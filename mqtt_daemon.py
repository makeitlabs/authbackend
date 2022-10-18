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
import subprocess
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

Config = ConfigParser.ConfigParser({})
Config.read('makeit.ini')
slack_token = Config.get('Slack','BOT_API_TOKEN')

# This is to remember last time user was announced via door entry audio
lastMemberAccess = {}

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

def send_slack_message(towho,message):
  sc = SlackClient(slack_token)
  if sc.rtm_connect():
    print "SLACK-SEND",towho,message
    res = sc.api_call(
        "chat.postMessage",
        channel=towho,
        text=message
        )

def convert_into_uppercase(a):
    return a.group(1) + a.group(2).upper()
    
# The callback for when a PUBLISH message is received from the server.
# 2019-01-11 17:09:01.736307
#def on_message(msg):
def on_message(client,userdata,msg):
    tool_cache={}
    resource_cache={}
    member_cache={}
    allow_slack_log=True
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
            toolDisplay=None
            nodename=None
            nodeId=None
            resourceId=None
            associated_resource=None
            log_event_type=None
            log_text=None

            send_slack=True
            send_slack_log_text=True
            send_slack_public=False
            send_slack_admin=True
            
            # base_topic+"/control/broadcast/acl/update"
            if topic[0]=="ratt" and topic[1]=="control" and topic[2]=="broadcast" and topic[3]=="acl" and topic[4]=="update":
                tool_cache={}
                resource_cache={}
                member_cache={}
            elif topic[0]=="ratt" and topic[1]=="status":
                if topic[2]=="node":
                    print topic
                    n=Node.query.filter(Node.mac == topic[3]).one_or_none()
                    t=Tool.query.join(Node,((Node.id == Tool.node_id) & (Node.mac == topic[3]))).one_or_none()
                    if t is None:
                      toolname="Node #"+str(topic[3])
                    else:
                      toolname=t.name
                if n:
                    n.last_ping=datetime.utcnow()
                    db.session.commit()
                elif topic[2]=="tool":
                    toolname=topic[3]

            subt=topic[4]
            sst=topic[5]
            member=None
            if 'toolId' in message: toolId=message['toolId']
            if 'nodeId' in message: nodeId=message['nodeId']
            if 'toolname' in message: toolname=message['toolname']
            if 'nodename' in message: nodename=message['noolname']
            if 'member' in message: member=message['member']

            if toolname and toolname in tool_cache:
                toolId = tool_cache[toolname]['id']
                toolDisplay = tool_cache[toolname]['displayname']
                resourceId = tool_cache[toolname]['resource_id']
                associated_resource = tool_cache[toolname]['data']
                toolSlackInfoText=tool_cache[toolname]['data']['slack_info_text']
            elif toolname:
                t = db.session.query(Tool.id,Tool.resource_id,Tool.displayname).filter(Tool.name==toolname)
                t = t.join(Resource,Resource.id == Tool.resource_id)
                t = t.add_column(Resource.slack_chan)
                t = t.add_column(Resource.slack_admin_chan)
                t = t.add_column(Resource.slack_info_text)
                t = t.one_or_none()
                if t:
                    tool_cache[toolname]={"id":t.id,"displayname":t.displayname, "resource_id":t.resource_id,"data": {
                        'slack_public_chan':t.slack_chan,
                        'slack_admin_chan':t.slack_admin_chan,
                        'slack_info_text':t.slack_info_text}}
                    toolId = tool_cache[toolname]['id']
                    toolDisplay = tool_cache[toolname]['displayname']
                    resourceId = tool_cache[toolname]['resource_id']
                    associated_resource = tool_cache[toolname]['data']
                    toolSlackInfoText=tool_cache[toolname]['data']['slack_info_text']
            
            if member and member in member_cache:
                memberId = member_cache[member]['id']
                memberSlackId = member_cache[member]['slack']
                #print "CACHE",memberId,"FROM",member
            elif member:
                q = Member.query.filter(Member.member==member)
                m = q.first()
                #print "QUERY MEMBER",q
                #print "RETURNED",m.id
                if m:
                    #print "CACHE",member,"=",m.id
                    member_cache[member]={'id':m.id,'slack':m.slack}
                    memberId=m.id
                    memberSlackId=m.slack


            #print "GOT DATA: Tool",toolname,toolId,"Node",nodename,nodeId,"Member",member,memberId,'=='

            if subt=="wifi":
                    # TODO throttle these!
                    #log_event_type = RATTBE_LOGEVENT_SYSTEM_WIFI.id
                    allow_slack_log=False
                    if n:
                      n.last_ping=datetime.utcnow()
                      n.strength=message['level'];
                      db.session.commit()
                    pass
            elif topic[0]=="ratt" and topic[1]=="status" and subt=="acl" and sst=="update":
                allow_slack_log=False
                if 'activeRecords' in message and 'totalRecords' in message:
                    log_text = "{0}/{1} active records - {2}".format(message['activeRecords'],message['totalRecords'],message['status'])
                else:
                    log_text = message['status']
                #log_event_type = RATTBE_LOGEVENT_TOOL_ACL_UPDATED.id
                if n:
                  n.last_update=datetime.utcnow()
                  db.session.commit()
            elif subt=="system":
                if sst=="boot":
                    log_event_type = RATTBE_LOGEVENT_SYSTEM_BOOT.id

                    fw_name = message['fw_name']

                    if fw_name=='ratt':
                        log_text = 'Application Started (' + fw_name + ' firmware ' + message['fw_version'] + ' mender artifact ' + message['mender_artifact'] + ')'
                    elif fw_name=='uratt':
                        reset_reasons = {
                            "power_on" : "Powered On",
                            "ext" : "External Reset",
                            "sw" : "Software Reset",
                            "panic" : "Panic",
                            "int_wdt" : "Interrupt Watchdog Reset",
                            "task_wdt" : "Task Watchdog Reset",
                            "deep_sleep" : "Wake from Deep Sleep",
                            "brownout" : "Power Brownout Reset",
                            "sdio" : "SDIO Reset",
                            "unknown" : "Unknown Reset" }

                        reason = message['reset_reason']
                        if reason in reset_reasons:
                            reason = reset_reasons[reason]

                        log_text = reason + ' (' + message['fw_name'] + ' firmware ' + message['fw_version'] + ' ' + message['fw_date'] + ' ' + message['fw_time'] + ')'
                    
                elif sst=="power":
                    state = message['state']  # lost | restored | shutdown
                    if state == "lost": log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_LOST.id
                    elif state == "restored": log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_RESTORED.id
                    elif state == "shutdown": log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_SHUTDOWN.id
                    else: 
                        log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_OTHER.id
                        send_slack = False
                        log_text = state

                elif sst=="ota_status":
                    status = message['status']
                    progress = int(message['progress'])

                    if (status == "downloading" and progress == 1) or status != "downloading":
                        log_event_type = RATTBE_LOGEVENT_SYSTEM_OTA.id
                        log_text = status.upper()
                    
                elif sst=="issue":
                    issue = message['issue'] # Text
                    log_event_type = RATTBE_LOGEVENT_TOOL_ISSUE.id
                    log_text = issue
                    send_slack_public = True

            elif subt=="personality":
                if sst=="safety":
                    # member
                    reason = message['reason'] # Failure reason text
                    log_event_type = RATTBE_LOGEVENT_TOOL_SAFETY.id
                    log_text = reason

                elif sst=="access":
                    if 'error' in message and message['error'] == True:
                        log_event_type = RATTBE_LOGEVENT_TOOL_UNRECOGNIZED_FOB.id
                        log_text = message['errorText'] + ' ' + message['errorExt']
                        send_slack = False
                    elif message['allowed']:
                        log_event_type = RATTBE_LOGEVENT_MEMBER_ENTRY_ALLOWED.id
                        if resourceId == 1:
                            if memberId not in lastMemberAccess or ((datetime.now() - lastMemberAccess[memberId]).total_seconds() > (3600*3)):
                                print "DOOR ENTRY FOR",memberId
                                lastMemberAccess[memberId] = datetime.now()
                                subprocess.Popen(
                                    ["/var/www/authbackend-ng/doorentry",str(memberId)], shell=False, stdin=None, stdout=None, stderr=None,
                                    close_fds=True)
                    else:
                        log_event_type = RATTBE_LOGEVENT_MEMBER_ENTRY_DENIED.id

                    send_slack_public = True
                    
                elif sst=="door_state":
                    st = message['state'] # open, closed
                    if st=="open":
                        log_event_type = RATTBE_LOGEVENT_DOOR_OPENED.id
                    elif st=="closed":
                        log_event_type = RATTBE_LOGEVENT_DOOR_CLOSED.id

                elif sst=="activity":
                    # member
                    active = message['active'] # Bool
                    if active:
                        log_event_type = RATTBE_LOGEVENT_TOOL_ACTIVE.id
                    else:
                        log_event_type = RATTBE_LOGEVENT_TOOL_INACTIVE.id

                    send_slack = False
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
                    send_slack_public = True
                    
                elif sst=="power":
                    powered = message['powered'].lower() == "True" # True or False
                    if powered:
                        log_event_type = RATTBE_LOGEVENT_TOOL_POWERON.id
                    else:
                        log_event_type = RATTBE_LOGEVENT_TOOL_POWEROFF.id

                elif sst=="login":
                    if 'error' in message and message['error'] == True:
                        log_event_type = RATTBE_LOGEVENT_TOOL_UNRECOGNIZED_FOB.id
                        log_text = message['errorText']
                        send_slack = False
                    else:
                        # member
                        usedPassword = False
                        if 'usedPassword' in message: usedPassword = message['usedPassword']
                        allowed = message['allowed'] # Bool

                        if allowed and usedPassword:
                            log_event_type = RATTBE_LOGEVENT_TOOL_LOGIN_COMBO.id
                        elif not allowed and usedPassword:
                            log_event_type = RATTBE_LOGEVENT_TOOL_COMBO_FAILED.id
                            if toolSlackInfoText and memberSlackId:
                                send_slack_message(memberSlackId,toolSlackInfoText)
                        elif allowed and not usedPassword:
                            log_event_type = RATTBE_LOGEVENT_TOOL_LOGIN.id
                        elif not allowed and not usedPassword:
                            log_event_type = RATTBE_LOGEVENT_TOOL_PROHIBITED.id
                            if toolSlackInfoText and memberSlackId:
                                send_slack_message(memberSlackId,toolSlackInfoText)

                        send_slack_public = True


                elif sst=="logout":
                    log_event_type = RATTBE_LOGEVENT_TOOL_LOGOUT.id
                    reason = message['reason']
                    enabledSecs = message['enabledSecs']
                    activeSecs = message['activeSecs']
                    idleSecs = message['idleSecs']

                    reasons = {
                        "explicit" : "Logged out",
                        "forced" : "Forced log out",
                        "timeout" : "Timed out",
                        "toolpower" : "Tool power turned off",
                        "emergencystop" : "Emergency Stop detected",
                        "other" : "Other logout reason" 
                    }

                    if reason in reasons:
                        reason = reasons[reason]
                    
                    log_text = "enabled for {0}, active for {1} - {2}".format(
                        seconds_to_timespan(enabledSecs),
                        seconds_to_timespan(activeSecs),
                        reason.upper())
                    usage= UsageLog()
                    usage.member_id = memberId
                    usage.tool_id = toolId
                    usage.resource_id = resourceId
                    usage.enabledSecs = enabledSecs
                    usage.activeSecs = activeSecs
                    usage.idleSecs = idleSecs
                    usage.time_reported = datetime.utcnow()
                    usage.time_logged = datetime.utcnow()
                    db.session.add(usage)
                    db.session.commit()

                    send_slack_public = True

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
                if not toolDisplay:
                    toolDisplay = toolname
                    
                if send_slack and log_event_type and toolDisplay and associated_resource and associated_resource['slack_admin_chan'] and allow_slack_log:
                  try:
                    slacktext=""
                    icon = ""
                    
                    if log_event_type in userdata['icons']: 
                      icon = userdata['icons'][log_event_type]

                    if member:
                      m = re.sub("(^|\s)(\S)", convert_into_uppercase, member.replace(".", " "))
                      slacktext += "*" + m + "* "
                        
                    
                    if log_event_type in userdata['events']:
                      if member:
                          t = "was %s at %s" % (userdata['events'][log_event_type].lower(), str(toolDisplay))
                      else:
                          t = "*%s* at %s" % (userdata['events'][log_event_type].upper(), str(toolDisplay))
                      slacktext += t
                      
                    else:
                      t = "Event #%s on %s" % (log_event_type, str(toolname))

                    if send_slack_log_text and log_text:
                      slacktext += "\n_" + log_text + "_"

                    color='#777777'
                    if log_event_type in userdata['colors']:
                        color=userdata['colors'][log_event_type]

                    time = "_" + datetime.now().strftime("%B %-d, %-I:%M:%S%p") + "_"

                    blocks = [{'type': 'context', 'elements': [{'type':'mrkdwn', 'text':icon + ' ' + time}, {'type': 'mrkdwn', 'text': slacktext } ] }]

                    # TODO FIEME This should be "send_slack_admin" - but Ham wanted only "public" messagse on their "admin" channel??
                    if send_slack_public and associated_resource['slack_admin_chan']:
                        res = sc.api_call(
                            'chat.postMessage',
                            channel=associated_resource['slack_admin_chan'],
                            blocks=json.dumps(blocks),
                            as_user=True
                        )
                        
                        if not res['ok']:
                            logger.error("error doing postMessage to \"%s\" admin chan: %s" % (associated_resource['slack_admin_chan'],res))

                    """
                    if send_slack_public and associated_resource['slack_public_chan']:
                        res = sc.api_call(
                            'chat.postMessage',
                            channel=associated_resource['slack_public_chan'],
                            blocks=json.dumps(blocks),
                            as_user=True
                        )
                        
                        if not res['ok']:
                            logger.error("error doing postMessage to public chan")
                    """

                            
                  except BaseException as e:
                    logger.error("ERROR=%s" % e)

                db.session.add(logevent)
                db.session.commit()
                #logger.warn('user_data_set start')
                #client.user_data_set(userdata)
                #logger.warn('user_data_set end')
                
    except BaseException as e:
        logger.error("LOG ERROR=%s PAYLOAD=%s" %(e,msg.payload))


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
      try:
              res = sc.api_call(
                "chat.postMessage",
                channel="#team-authit-devs",
                text="AuthIt Slack/MQTT daemon is on the air... :tada:"
              )
              if res['ok'] == False:
                logger.error("Slack MQTT test message failed: %s"%res['error'])

              #res = sc.api_call(
              #  "chat.postMessage",
              #  channel="#monitoring-security",
              #  text="This is a test :tada:"
              #)
              #if res['ok'] == False:
              #  logger.error("Slack MQTT test message failed: %s"%res['error'])
      except:
        pass
      while True:
          # TODO BKG BUG re-add error-safe logic here
          try:
            callbackdata={'slack_context':sc}
            callbackdata['events']=eventtypes.get_events()
            callbackdata['icons']=eventtypes.get_event_slack_icons()
            callbackdata['colors']=eventtypes.get_event_slack_colors()
            callbackdata['msg_track'] = {}
            
            sub.callback(on_message, "ratt/#",userdata=callbackdata, **opts)
            sub.loop_forever()
            sub.loop_misc()
            time.sleep(1)
            msg = sub.simple("ratt/#", hostname=host,port=port,**opts)
            print("%s %s" % (msg.topic, msg.payload))
          except KeyboardInterrupt:    #on_message(msg)
            sys.exit(0)
          except:
            print "EXCEPT"
            time.sleep(1)
