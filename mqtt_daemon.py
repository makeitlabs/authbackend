#!/usr/bin/python2
"""
vim:tabstop=2:expandtab
MakeIt Labs Authorization System, v0.4

This is a daemon only used to log stuff via MQTT
"""

from authlibs.eventtypes import *
import sqlite3, re, time
from authlibs.db_models import db,  Role, UserRoles, Member, Resource, AccessByMember, Logs, Tool, UsageLog, Node
import argparse
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from flask_sqlalchemy import SQLAlchemy
from authlibs import utilities as authutil
from slackclient import SlackClient
import json
import ConfigParser,sys,os
import paho.mqtt.client as mqtt
import paho.mqtt.subscribe as sub
from datetime import datetime
from authlibs.init import authbackend_init, createDefaultUsers
import requests,urllib,urllib2
import logging, logging.handlers
from  authlibs import eventtypes


## SETUP LOGGING

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logger=logging.getLogger()
handler = logging.handlers.RotatingFileHandler(
    "/tmp/mqtt_dameon.log", maxBytes=(1048576*5), backupCount=7)
handler.setLevel(logging.DEBUG)
format = logging.Formatter("%(asctime)s:%(levelname)s:%(module)s:%(message)s")
handler.setFormatter(format)
ch = logging.StreamHandler()
format = logging.Formatter("%(module)s:%(levelname)s:%(message)s")
ch.setFormatter(format)
ch.setLevel(logging.DEBUG)

logger.addHandler(ch)
logger.addHandler(handler)


def get_mqtt_opts(app):
  Config = ConfigParser.ConfigParser({})
  Config.read('makeit.ini')
  mqtt_opts={}
  mqtt_base_topic = Config.get("MQTT","BaseTopic")
  mqtt_opts['hostname'] = Config.get("MQTT","BrokerHost")
  mqtt_opts['port'] = Config.getint("MQTT","BrokerPort")
  if Config.has_option("MQTT","keepalive"):
      mqtt_opts['keepalive']=Config.getint("MQTT","keepalive")
  if Config.has_option("MQTT","SSL") and Config.getboolean("MQTT","SSL"):
      mqtt_opts['tls']={}
      mqtt_opts['tls']['ca_certs'] = Config.get('MQTT_SSL', 'ca_certs')
      mqtt_opts['tls']['certfile'] = Config.get('MQTT_SSL', 'certfile')
      mqtt_opts['tls']['keyfile'] = Config.get('MQTT_SSL', 'keyfile')

      if Config.has_option('MQTT_SSL', 'tls_version'):
          mqtt_opts['tls']['tls_version'] = Config.get('MQTT_SSL', 'tls_version')

      if Config.has_option('MQTT_SSL', 'ciphers'):
          mqtt_opts['tls']['ciphers'] = Config.get('MQTT_SSL', 'ciphers')

  if Config.has_option("MQTT","username"):
      mqtt_opts['auth']={'username':app.globalConfig.Config.get("MQTT","username"),'password':app.globalConfig.Config.get("MQTT","password")}
  slack_token = Config.get('Slack','BOT_API_TOKEN')
  return (mqtt_base_topic,mqtt_opts,slack_token)

def seconds_to_timespan(s):
    hours, remainder = divmod(s, 3600)
    minutes, seconds = divmod(remainder, 60)
    return '{:02}:{:02}:{:02}'.format(int(hours), int(minutes), int(seconds))

# The callback for when a PUBLISH message is received from the server.
# 2019-01-11 17:09:01.736307
#def on_message(msg):
def on_message(client,userdata,msg):
    tool_cache={}
    resource_cache={}
    member_cache={}
    sc = userdata['slack_context']
    try:
        with app.app_context():
            log=Logs()
            print "FROM WIRE",msg.topic,msg.payload
            message = json.loads(msg.payload)
            topic=msg.topic.split("/")

            # Is this a RATT status message?
            toolname=None
            member=None
            memberId=None
            toolId=None
            nodename=None
            nodeId=None
            resourceId=None
            associated_resource=None
            log_event_type=None
            log_text=None

            # base_topic+"/control/broadcast/acl/update"
            if topic[0]=="ratt" and topic[1]=="control" and topic[2]=="broadcast" and topic[3]=="acl" and topic[4]=="update":
                tool_cache={}
                resource_cache={}
                member_cache={}
            elif topic[0]=="ratt" and topic[1]=="status":
                if topic[2]=="node":
                    t=Tool.query.join(Node,((Node.id == Tool.node_id) & (Node.mac == topic[3]))).one_or_none()
                    if t is None:
                      toolname="Node #"+str(topic[3])
                    else:
                      toolname=t.name
                elif topic[2]=="tool":
                    toolname=topic[3]

            subt=topic[4]
            sst=topic[5]
            member=None
            if 'toolId' in message: toolId=message['toolId']
            if 'nodeId' in message: toolId=message['noolId']
            if 'toolname' in message: toolname=message['toolname']
            if 'nodename' in message: nodename=message['noolname']
            if 'member' in message: member=message['member']

            if toolname and toolname in tool_cache:
                toolId = tool_cache[toolname]['id']
                resourceId = tool_cache[toolname]['resource_id']
                associated_resource = tool_cache[toolname]['data']
            elif toolname:
                t = db.session.query(Tool.id,Tool.resource_id).filter(Tool.name==toolname)
                t = t.join(Resource,Resource.id == Tool.resource_id)
                t = t.add_column(Resource.slack_chan)
                t = t.add_column(Resource.slack_admin_chan)
                t = t.add_column(Resource.slack_info_text)
                t = t.one_or_none()
                if t:
                    tool_cache[toolname]={"id":t.id,"resource_id":t.resource_id,"data": {
                        'slack_chan':t.slack_chan,
                        'slack_admin_chan':t.slack_admin_chan,
                        'slack_info_text':t.slack_info_text}}
                    toolId = tool_cache[toolname]['id']
                    resourceId = tool_cache[toolname]['resource_id']
                    associated_resource = tool_cache[toolname]['data']
            
            if member and member in member_cache:
                memberId = member_cache[member]
                #print "CACHE",memberId,"FROM",member
            elif member:
                q = db.session.query(Member.id).filter(Member.member==member)
                m = q.first()
                #print "QUERY MEMBER",q
                #print "RETURNED",m.id
                if m:
                    #print "CACHE",member,"=",m.id
                    member_cache[member]=m.id
                    memberId=m.id


            print "GOT DATA: Tool",toolname,toolId,"Node",nodename,nodeId,"Member",member,memberId,'=='

            if subt=="wifi":
                    # TODO throttle these!
                    #log_event_type = RATTBE_LOGEVENT_SYSTEM_WIFI.id
                    pass
            elif subt=="system":
                if sst=="power":
                    state = message['state']  # lost | restored | shutdown
                    if state == "lost": log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_LOST.id
                    elif state == "restored": log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_RESTORED.id
                    elif state == "shutdown": log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_SHUTDOWN.id
                    else: 
                        log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_OTHER.id
                        log_text = state
                        
                elif sst=="issue":
                    issue = message['issue'] # Text
                    log_event_type = RATTBE_LOGEVENT_TOOL_ISSUE.id
                    log_text = issue
            elif subt=="personality":
                if sst=="safety":
                    # member
                    reason = message['reason'] # Failure reason text
                    log_event_type = RATTBE_LOGEVENT_TOOL_SAFETY.id
                    log_text = reason
                elif sst=="activity":
                    # member
                    active = message['active'] # Bool
                    if active:
                        log_event_type = RATTBE_LOGEVENT_TOOL_ACTIVE.id
                    else:
                        log_event_type = RATTBE_LOGEVENT_TOOL_INACTIVE.id
                elif sst=="state":
                    phase = message['phase'] # ENTER, ACTIVE, EXIT 
                    state = message['state'] # Text
                elif sst=="lockout":
                    state = message['state'] # pending | locked | unlocked
                    if state=="pending": log_event_type = RATTBE_LOGEVENT_TOOL_LOCKOUT_PENDING.id
                    elif state=="locked": log_event_type = RATTBE_LOGEVENT_TOOL_LOCKOUT_LOCKED.id
                    elif state=="unlocked": log_event_type = RATTBE_LOGEVENT_TOOL_LOCKOUT_UNLOCKED.id
                    else: log_event_type=RATTBE_LOGEVENT_TOOL_LOCKOUT_OTHER.id
                    log_text = reason
                elif sst=="power":
                    powered = message['powered'].lower() == "True" # True or False
                    if powered:
                        log_event_type = RATTBE_LOGEVENT_TOOL_POWERON.id
                    else:
                        log_event_type = RATTBE_LOGEVENT_TOOL_POWEROFF.id
                elif sst=="login":
                    # member
                    usedPassword = False
                    if 'usedPassword' in message: usedPassword = message['usedPassword']
                    allowed = message['allowed'] # Bool

                    if allowed and usedPassword:
                        log_event_type = RATTBE_LOGEVENT_TOOL_LOGIN_COMBO.id
                    elif not allowed and usedPassword:
                        log_event_type = RATTBE_LOGEVENT_TOOL_PROHIBITED.id
                    elif allowed and not usedPassword:
                        log_event_type = RATTBE_LOGEVENT_TOOL_LOGIN.id
                    elif not allowed and not usedPassword:
                        log_event_type = RATTBE_LOGEVENT_TOOL_COMBO_FAILED.id

                    if 'error' in message:
                        error = message['error'] # Bool
                    else:
                        error = False
                    if 'errorText' in message:
                        errorText = message['errorText'] # text
                    else:
                        errorText=None

                    log_text = errorText

                elif sst=="logout":
                    print "LOGOUT"
                    log_event_type = RATTBE_LOGEVENT_TOOL_LOGOUT.id
                    reason = message['reason']
                    enabledSecs = message['enabledSecs']
                    activeSecs = message['activeSecs']
                    idleSecs = message['idleSecs']

                    log_text = "enabled {0} active {1} idle {2} - {3}".format(
                        seconds_to_timespan(enabledSecs),
                        seconds_to_timespan(activeSecs),
                        seconds_to_timespan(idleSecs),
                        reason)
                    usage= UsageLog()
                    usage.member_id = memberId
                    usage.tool_id = toolId
                    usage.resource_id = resourceId
                    usage.enabledSecs = enabledSecs
                    usage.activeSecs = activeSecs
                    usage.idleSecs = idleSecs
                    usage.timeReported = datetime.now()
                    db.session.add(usage)
                    db.session.commit()

            if log_event_type:
                logevent = Logs()
                logevent.member_id=memberId
                logevent.resource_id=resourceId
                logevent.tool_id=toolId
                # DB will default to current UTC datetime
                #logevent.time_reported=datetime.now()
                #logevent.time_logged=datetime.now() 
                logevent.event_type = log_event_type
                logevent.message = log_text

                # Do slack notification
                if log_event_type and toolname and associated_resource and associated_resource['slack_admin_chan']:
                  try:
                    slacktext="" 
                    if log_event_type in userdata['icons']: 
                      slacktext += userdata['icons'][log_event_type]+" "
                    if member: slacktext += "*"+member+"* "
                    if log_event_type in userdata['events']:
                      slacktext += "%s: %s "%  (str(toolname),userdata['events'][log_event_type])
                    else:
                      slacktext += "%s: Event #%s" % (str(toolname),log_event_type)
                    if log_text: slacktext += " "+log_text
                    res = sc.api_call(
                      "chat.postMessage",
                      channel=associated_resource['slack_admin_chan'],
                      text=slacktext
                    )
                  except BaseException as e:
                    print "ERROR",e
                db.session.add(logevent)
                db.session.commit()
    except BaseException as e:
        print "LOG ERROR",e,"PAYLOAD",msg.payload
        print "NOW4"

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--command",help="Special command",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    app=authbackend_init(__name__)

    with app.app_context():
      # The callback for when the client receives a CONNACK response from the server.
      (base_topic,opts,slack_api_token) = get_mqtt_opts(app)
      sc = SlackClient(slack_api_token)
      # TODO BKG BUG change channel
      res = sc.api_call(
        "chat.postMessage",
        channel="#test-resource-admins",
        text="mqtt daemon alive :tada:"
      )
      if res['ok'] == False:
        logger.error("Slack MQTT test message failed: %s"%res['error'])
      while True:
          # TODO BKG BUG re-add error-safe logic here
          #try:
            callbackdata={'slack_context':sc}
            callbackdata['events']=eventtypes.get_events()
            callbackdata['icons']=eventtypes.get_event_slack_icons()
            sub.callback(on_message, "ratt/#",userdata=callbackdata, **opts)
            sub.loop_forever()
            sub.loop_misc()
            time.sleep(1)
            msg = sub.simple("ratt/#", hostname=host,port=port,**opts)
            print("%s %s" % (msg.topic, msg.payload))
            """
          except KeyboardInterrupt:    #on_message(msg)
            sys.exit(0)
          except:
            print "EXCEPT"
            time.sleep(1)
            """
