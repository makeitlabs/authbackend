#!/usr/bin/python3
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
from slack import WebClient as SlackClient
import json
import subprocess
import configparser,sys,os
import paho.mqtt.client as mqtt
# NO import paho.mqtt.subscribe as sub
from datetime import datetime
from authlibs.init import authbackend_init, createDefaultUsers
import requests,urllib
import logging, logging.handlers
from  authlibs import eventtypes
import redis

global client


## SETUP LOGGING

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logger=logging.getLogger()
handler.setLevel(logging.DEBUG)
format = logging.Formatter("%(asctime)s:%(levelname)s:%(module)s:%(message)s")
handler.setFormatter(format)
ch = logging.StreamHandler()
format = logging.Formatter("%(module)s:%(levelname)s:%(message)s")
ch.setFormatter(format)
ch.setLevel(logging.DEBUG)

logger.addHandler(ch)
logger.addHandler(handler)

Config = configparser.ConfigParser({})
Config.read('makeit.ini')
slack_token = Config.get('Slack','BOT_API_TOKEN')
speakbot_slack_token = Config.get('Speakbot','slack_token')

# This is to remember last time user was announced via door entry audio
lastMemberAccess = {}


def custom_decoder(obj):
    if 'time' in obj:
        obj['time']= datetime.fromisoformat(obj['time'])
    return obj

# Minisplit temperatures
def ingest_record(minisplit,r,src):
    rr= r.get("minisplit_data/"+minisplit)
    if rr is None:
        datapoints = []
    else:
        datapoints = json.loads(rr, object_hook=custom_decoder)
    dest = {}
    dest['time'] = datetime.strptime(src['time'], "%a %b %d %H:%M:%S %Y")
    dest['setpoint'] = src['setpoint']
    dest['roomTemp'] = src['roomTemp']
    dest['operating'] = 0 if src['operating']=='OFF' else 1
    #print ("DEST",dest)
    datapoints.append(dest)
    datapoints = datapoints[-90:]
    #print ("DATAPOINTS:", datapoints)

    rr= r.get("minisplit_hours/"+minisplit)
    if rr is None:
        hours = []
    else:
        hours = json.loads(rr, object_hook=custom_decoder)


    if (len(hours) == 0) or (dest['time'] >= hours[-1]['time'].replace(minute=59,second=59,microsecond=999999)):
        hour = {}
        hour['time'] =  dest['time'].replace(minute=0,second=0,microsecond=0)
        hours.append(hour)

    #print ("HOURS:", hours)
    # Re-average last hour
    count=0
    setpoint=0
    roomTemp=0
    operating=0
    starttime = hours[-1]['time']
    endtime = hours[-1]['time'].replace(minute=59,second=59,microsecond=999999)
    for e in datapoints:
        if (starttime <= e['time']) and (e['time'] <= endtime):
            count += 1
            roomTemp += e['roomTemp']
            setpoint += e['setpoint']
            operating += e['operating']
    if count == 0: count=1
    hours[-1]['roomTemp'] = roomTemp/count
    hours[-1]['setpoint'] = setpoint/count
    hours[-1]['operating'] = operating/count

    hours = hours[-(24*14):]

    r.set("minisplit_data/"+minisplit,json.dumps(datapoints, default=str))
    r.set("minisplit_hours/"+minisplit,json.dumps(hours,default=str))

def get_mqtt_opts(app):
  Config = configparser.ConfigParser({})
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
    print ("SLACK-SEND",towho,message)
  res = sc.api_call(
    "chat.postMessage",
    json = {
        'channel':towho,
        'text':message
    }
  )
  if res['ok'] == False:
    logger.error("Slack MQTT test message failed: %s"%res['error'])

def convert_into_uppercase(a):
    return a.group(1) + a.group(2).upper()
    
def on_connect(client,userdata,flags,res):
    print ("MQTT CONNECTED")
    client.subscribe("ratt/#")
    client.subscribe("facility/minisplit/report/#")
    client.subscribe("facility/alarm/system")
    client.publish("displayboard/read/status","CONNECTED")
# The callback for when a PUBLISH message is received from the server.
# 2019-01-11 17:09:01.736307
#def on_message(msg):
def on_message(client,userdata,msg):
    global verbose
    tool_cache={}
    resource_cache={}
    member_cache={}
    allow_slack_log=True
    sc = userdata['slack_context']
    try:
        with app.app_context():
            log=Logs()
            if (verbose>=2): print ("FROM WIRE",msg.topic,msg.payload)
            try:
                message = json.loads(msg.payload)
            except:
                message = {'payload':  msg.payload}
            topic=msg.topic.split("/")

            # Is this a RATT status message?
            toolname=None
            member=None
            memberId=None
            memberNickname=None
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
            send_mqtt_event=None
            send_mqtt_status=None
            
            if topic[0]=="facility" and topic[1]=="alarm" and topic[2]=="system":
                print ("Facility Alarm:",message)
                if message['payload']=="armed":
                    speech = "Attention: Alarm Activated"
                    url = 'http://cgimisc:8091/slack'
                    data = {
                        'command': 'flash',
                        'text': speech,
                        'token':speakbot_slack_token
                    }
                    urllib.request.urlopen(url,data)
                    
            elif topic[0]=="printers":
                #printers/00m09d470802228 {"name": "MakeIt Left", "status": "RUNNING", "percent": 40, "min_remaining": 20, "reported": "2026-06-09T17:36:42.238514", "job": "AJ_HATHAWAY-Foxy"}
                #printers/00M09D470802228 {"name": "MakeIt Left", "status": "FINISH", "percent": 100, "min_remaining": 0, "reported": "2026-06-15T09:45:55.293886", "job": "jay_briand-JASK\u00d3\u0141KA_MOLD"}
                #printers/00M09D462500690 {"name": "MakeIt Right", "status": "FINISH", "percent": 100, "min_remaining": 0, "reported": "2026-06-15T09:45:06.713445", "job": "jay_briand-PRED8_VIBE_mold"}
                #printers/0938aj632500655 {"name": "Gamera", "status": "FAILED", "percent": 0, "min_remaining": 0, "reported": "2026-06-09T17:36:42.425520", "job": "dose_divider3_v12"}
                #printers/0938AJ632500655 {"name": "Gamera", "status": "FINISH", "percent": 100, "min_remaining": 0, "reported": "2026-06-15T09:45:36.165388", "job": "Tom_Doucet_P-T800_T_121_body"}
                #printers/0948AB510700445 {"name": "Godzilla", "status": "IDLE", "percent": 0, "min_remaining": 0, "reported": "2026-06-09T22:11:14.196290", "job": ""}
                r = redis.Redis()
                j = json.loads(msg.payload)
                printer = topic[1]
                r.set("printer/"+printer,msg.payload)
                return

            elif topic[0]=="facility" and topic[1]=="minisplit" and topic[2]=="report":
                r = redis.Redis()
                minisplit = topic[3]
                #print ("GOT",minisplit,message)
                r.set("minisplit/"+minisplit,msg.payload)

                # minisplit-class {'power': 'ON', 'setpoint': 66, 'roomTemp': 66, 'mode': 'HEAT', 'fan': 'AUTO', 'ip': '10.25.6.207', 'rssid': -52, 'fw': '0.0.9', 'time': 'Tue Mar 26 12:07:26 2024', 'managed': 'HEAT', 'managed_setpoint': 67, 'override_setpoint': 72, 'override_time': 120, 'override_end': '', 'managed_setpoint_unoccupied': 52, 'ir_interval': 15, 'operating': 'ON', 'alarm': 'Disarmed', 'last_ir': 'Tue Mar 26 12:01:15 2024'}
                j = json.loads(msg.payload)
                ingest_record(minisplit,r,j)

                # We return here because we would get an index error below looking up subtopic
                return

            # base_topic+"/control/broadcast/acl/update"
            if topic[0]=="ratt" and topic[1]=="control" and topic[2]=="broadcast" and topic[3]=="acl" and topic[4]=="update":
                tool_cache={}
                resource_cache={}
                member_cache={}
            elif topic[0]=="ratt" and topic[1]=="status":
                if topic[2]=="node":
                    if (verbose >= 1): print ("RATT Node Status",topic)
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
            if subt=="ping": return
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
                t = t.add_columns(Resource.slack_chan)
                t = t.add_columns(Resource.slack_admin_chan)
                t = t.add_columns(Resource.slack_info_text)
                t = t.add_columns(Resource.event_mqtt_topic)
                t = t.one_or_none()
                if t:
                    tool_cache[toolname]={"id":t.id,"displayname":t.displayname, "resource_id":t.resource_id,"data": {
                        'slack_public_chan':t.slack_chan,
                        'slack_admin_chan':t.slack_admin_chan,
                        'event_mqtt_topic':t.event_mqtt_topic,
                        'slack_info_text':t.slack_info_text}}
                    toolId = tool_cache[toolname]['id']
                    toolDisplay = tool_cache[toolname]['displayname']
                    resourceId = tool_cache[toolname]['resource_id']
                    associated_resource = tool_cache[toolname]['data']
                    toolSlackInfoText=tool_cache[toolname]['data']['slack_info_text']
            
            if member and member in member_cache:
                memberId = member_cache[member]['id']
                memberSlackId = member_cache[member]['slack']
                memberNickname = member_cache[member]['nickname']
                #print "CACHE",memberId,"FROM",member
            elif member:
                q = Member.query.filter(Member.member==member)
                m = q.first()
                #print "QUERY MEMBER",q
                #print "RETURNED",m.id
                if m:
                    #print "CACHE",member,"=",m.id
                    member_cache[member]={'id':m.id,'slack':m.slack,'nickname':m.nickname}
                    memberId=m.id
                    memberNickname = m.nickname
                    memberSlackId=m.slack


            #print "GOT DATA: Tool",toolname,toolId,"Node",nodename,nodeId,"Member",member,memberId,'=='

            if subt=="wifi":
                    # TODO throttle these!
                    #log_event_type = RATTBE_LOGEVENT_SYSTEM_WIFI.id
                    allow_slack_log=False
                    if n:
                      n.last_ping=datetime.utcnow()
                      n.strength=message['level'];
                      n.ip_addr = message['ip'] if 'ip'  in message else ""
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

                    if fw_name=='goratt':
                        log_text = 'Application Started (' + fw_name + ' firmware ' + message['fw_version']  + ')'
                    elif fw_name=='ratt':
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
                    if state == "lost": 
                        log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_LOST.id
                        send_mqtt_status={}
                    elif state == "restored": 
                        log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_RESTORED.id
                    elif state == "shutdown": 
                        log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_SHUTDOWN.id
                        send_mqtt_status={}
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

                elif sst == 'storagepass':
                    log_event_type = RATTBE_LOGEVENT_MEMBER_ENTRY_STORAGEPASS.id
                    log_text = "Temporary Storage Pass Issued"
                elif sst=="access":
                    if 'error' in message and message['error'] == True:
                        #log_event_type = RATTBE_LOGEVENT_TOOL_UNRECOGNIZED_FOB.id
                        #log_text = message['errorText'] + ' ' + message['errorExt']
                        #send_slack = False
                        pass
                    elif message['allowed']:
                        log_event_type = RATTBE_LOGEVENT_MEMBER_ENTRY_ALLOWED.id
                        if resourceId == 1:
                            if memberId not in lastMemberAccess or ((datetime.now() - lastMemberAccess[memberId]).total_seconds() > (3600*18)):
                                print ("DOOR ENTRY FOR",memberId)
                                lastMemberAccess[memberId] = datetime.now()
                                opts = []
                                now = datetime.now()
                                if (now.weekday() ==3) and ((now.hour >= 16) and (now.hour <= 22)):
                                    opts += [ "--quiet" ]
                                else:
                                    subprocess.Popen(
                                      ["/var/www/authbackend/doorentry",str(memberId)]+opts, shell=False, stdin=None, stdout=None, stderr=None,
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
                    elif state=="locked": 
                        log_event_type = RATTBE_LOGEVENT_TOOL_LOCKOUT_LOCKED.id
                        send_mqtt_event={'status':"Lockout","text":reason}
                    elif state=="unlocked": 
                        log_event_type = RATTBE_LOGEVENT_TOOL_LOCKOUT_UNLOCKED.id
                        send_mqtt_event={}
                    else: log_event_type=RATTBE_LOGEVENT_TOOL_LOCKOUT_OTHER.id
                    log_text = reason
                    send_slack_public = True
                    
                elif sst=="power":
                    powered = message['powered'].lower() == "True" # True or False
                    if powered:
                        log_event_type = RATTBE_LOGEVENT_TOOL_POWERON.id
                    else:
                        send_mqtt_status={}
                        log_event_type = RATTBE_LOGEVENT_TOOL_POWEROFF.id

                elif sst=="login":
                    if 'error' in message and message['error'] == True:
                        #log_event_type = RATTBE_LOGEVENT_TOOL_UNRECOGNIZED_FOB.id
                        #log_text = message['errorText']
                        #send_slack = False
                        pass
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
                            send_mqtt_event={'Title':"In-Use",'Timeout':30}
                            m=""
                            if member:
                              m= re.sub("(^|\s)(\S)", convert_into_uppercase, member.replace(".", " "))
                            send_mqtt_status={'status':"In-Use","text":m}
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
                    payTier = 0

                    if 'payTier' in message:
                        payTier = message['payTier']

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
                    if (payTier == 1):
                        log_text += f" - Free Tier"
                    elif (payTier > 0):
                        log_text += f" - Tier {payTier}"
                    usage= UsageLog()
                    usage.member_id = memberId
                    usage.tool_id = toolId
                    usage.resource_id = resourceId
                    usage.enabledSecs = enabledSecs
                    usage.activeSecs = activeSecs
                    usage.idleSecs = idleSecs
                    usage.payTier = payTier
                    usage.time_reported = datetime.utcnow()
                    usage.time_logged = datetime.utcnow()
                    db.session.add(usage)
                    db.session.commit()
                    send_mqtt_event={'Title':"Finished",'Timeout':30,"Message":reason}
                    send_mqtt_status={}

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

                    
                if send_mqtt_event is not None and associated_resource['event_mqtt_topic']:
                    m = re.sub("(^|\s)(\S)", convert_into_uppercase, member.replace(".", " "))
                    if 'Message' in send_mqtt_event:
                        send_mqtt_event['Message'] = send_mqtt_event['Message'].replace('{member}',m)
                    else:
                        send_mqtt_event['Message'] = m
                    client.publish(associated_resource['event_mqtt_topic'],json.dumps(send_mqtt_event,indent=2))

                # displayboard MQTT event bus
                if send_slack:
                    try:
                        mqttevt = {}
                        mqttevt['color']='#777777'
                        mqttevt['eventcode']=log_event_type
                        if log_event_type in userdata['events']:
                            mqttevt['eventstr']=userdata['events'][log_event_type]
                        if log_event_type in userdata['icons']: 
                          mqttevt['icon'] = userdata['icons'][log_event_type]

                        if member:
                          mqttevt['member'] = re.sub("(^|\s)(\S)", convert_into_uppercase, member.replace(".", " "))
                          if memberNickname is not None and memberNickname.strip() != "":
                            mqttevt['nickname'] = re.sub("(^|\s)(\S)", convert_into_uppercase, memberNickname.replace(".", " "))
                        mqttevt['tool'] = str(toolDisplay)
                        client.publish("displayboard/read/event",json.dumps(mqttevt,indent=2))
                    except BaseException as e:
                        logger.error ("Send MQTT Failed %s" % str(e))

                if send_mqtt_status is not None and toolname is not None:
                    logger.error(f"Update Displayboard Status for {toolname} {toolDisplay} {send_mqtt_status}")
                    try:
                        if send_mqtt_status:
                            send_mqtt_status['name']=toolDisplay
                            client.publish("displayboard/read/status/"+toolname,json.dumps(send_mqtt_status,indent=2),retain=True)
                        else:
                            # If dictionary is empty, send an empty payload with retain flag to CLEAR the retained message
                            client.publish("displayboard/read/status/"+toolname,"",retain=True)
                    except BaseException as e:
                        logger.error ("Send MQTT status Failed %s"%str(e))
                    


                if send_slack and log_event_type and toolDisplay and associated_resource and associated_resource['slack_admin_chan'] and allow_slack_log:
                  try:
                    slacktext=""
                    rawtext=""
                    icon = ""
                    
                    if log_event_type in userdata['icons']: 
                      icon = userdata['icons'][log_event_type]

                    if member:
                      m = re.sub("(^|\s)(\S)", convert_into_uppercase, member.replace(".", " "))
                      slacktext += "*" + m + "* "
                      rawtext += m+" "
                        
                    
                    if log_event_type in userdata['events']:
                      if member:
                          t = "was %s at %s" % (userdata['events'][log_event_type].lower(), str(toolDisplay))
                          rawtext += t
                      else:
                          t = "*%s* at %s" % (userdata['events'][log_event_type].upper(), str(toolDisplay))
                          rawtext += "%s at %s" % (userdata['events'][log_event_type].upper(), str(toolDisplay))
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
                        for chan in associated_resource['slack_admin_chan'].split(","):
                            res = sc.api_call(
                              "chat.postMessage",
                              json = {
                                  'channel':chan,
                                  'blocks': blocks,
                                  #'text': icon + " " + time + " " + slacktext,
                                  'as_user':True
                              }
                            )
                            
                            if not res['ok']:
                                logger.error("error doing postMessage to \"%s\" admin chan: %s" % (associated_resource['slack_admin_chan'],res))
                        if rawtext != "":
                            client.publish("displayboard/read/resource/post",json.dumps({"Message":rawtext},indent=2))

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
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    logger.error("LOG ERROR=%s LINE=%d TOPIC=%s PAYLOAD=%s" %(e,exc_tb.tb_lineno,msg.topic,msg.payload))

                db.session.add(logevent)
                db.session.commit()
                #logger.warn('user_data_set start')
                #client.user_data_set(userdata)
                #logger.warn('user_data_set end')
                
    except BaseException as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logger.error("LOG ERROR=%s LINE=%d TOPIC=%s PAYLOAD=%s" %(e,exc_tb.tb_lineno,msg.topic,msg.payload))


def on_connect(client, userdata, flags, rc):
    client.subscribe("ratt/#")
    client.subscribe("facility/minisplit/report/#")
    client.subscribe("facility/alarm/system")
    client.subscribe("printers/#")

if __name__ == '__main__':
    global verbose
    red = redis.Redis()
    parser=argparse.ArgumentParser()
    parser.add_argument("--command",help="Special command",action="store_true")
    parser.add_argument("--verbose","-v",help="Verbosity",action="count",default=0)
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    verbose = args.verbose
    app=authbackend_init(__name__)

    with app.app_context():
      # The callback for when the client receives a CONNACK response from the server.
      (base_topic,opts,slack_api_token) = get_mqtt_opts(app)
      sc = SlackClient(slack_api_token)
      # TODO BKG BUG change channel
      try:
              res = sc.api_call(
                "chat.postMessage",
                json = {
                    'channel':"#team-authit-devs",
                    'text':"AuthIt Slack/MQTT daemon is on the air... :tada:"
                }
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
      except BaseException as e:
        print ("TRY POST MESSAGE EXCEPT",e)
      while True:
          # TODO BKG BUG re-add error-safe logic here
          try:
            callbackdata={'slack_context':sc}
            callbackdata['events']=eventtypes.get_events()
            callbackdata['icons']=eventtypes.get_event_slack_icons()
            callbackdata['colors']=eventtypes.get_event_slack_colors()
            callbackdata['msg_track'] = {}
            #print (opts)
            sub = mqtt.Client(userdata=callbackdata)
            sub.tls_set(**opts['tls'])
            sub.connect(opts['hostname'],port=opts['port'],keepalive=opts['keepalive'])
            #sub.callback(on_message, "ratt/#",userdata=callbackdata, **opts)
            sub.on_message = on_message
            sub.on_connect = on_connect
            sub.loop_forever()
            print ("THIS SHOLD NEVER HAPPEN!")
            sub.loop_misc()
            time.sleep(1)
            msg = sub.simple("ratt/#", hostname=host,port=port,**opts)
            print("%so %s" % (msg.topic, msg.payload))
          except KeyboardInterrupt:    #on_message(msg)
            sys.exit(0)
          except BaseException as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error("LOG ERROR=%s LINE=%d" %(e,exc_tb.tb_lineno))
            time.sleep(1)
