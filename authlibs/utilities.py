#!/usr/bin/env python
# Utilities for MakeIt Labs

import hashlib
import string
import sqlite3
import re
import pytz
from datetime import datetime,date
from flask import g,current_app
from flask_user import current_user
from db_models import db, AccessByMember, Member, Resource, Logs
import json
import paho.mqtt.publish as mqtt_pub
import logging


    
def hash_rfid(rfid):
    "Given an integer RFID, create a hashed value for storage"
    if rfid == 'None':
        return None
    else:
        try:
            m = hashlib.sha224()
            rfidStr = "%.10d"%(int(rfid))
            m.update(str(rfidStr).encode())
            return m.hexdigest()
        except:
            return None

def rfid_validate(ntag):
	result=None
	if ntag is None: return None
	if len(ntag) != 10: return None
	try:
		result=int(ntag)
	except:
		return None
	return result

def _utcTimestampToDatetime(ts):
    """Convert a UTC timestamp to my local time"""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")

def _safeemail(unsafe_str):
    """Sanitize email addresses strings used in some oeprations"""
    keepcharacters = ('.','_','@','-')
    return "".join(c for c in unsafe_str if c.isalnum() or c in keepcharacters).strip()

def _safestr(s):
    """Sanitize input strings used in some operations"""
    keepcharacters = ('-',' ','.')
    return "".join(c for c in s if c.isalnum() or c in keepcharacters).strip()

def _joinNameString(s):
    '''Replace all numerics and non-alphanumerics in a name string, then concatenate using . ''' 
    newstr = re.findall(r"[\w]+",s)
    #newid = m['name'].replace(" ",".")
    return ".".join(newstr)

def alertAdmins(severity,msg):
    '''Alert admins of an issue. Intended to be configurable for notification mechanisms'''
    pass

def nameToFirstLast(namestr):
    names = namestr.split(".")
    first = names[0]
    last = " ".join(names[1:])
    return {'first': first, 'last': last}

# TODO This doesn't return in UTC - It should
def parse_datetime(dt):
  tz=pytz.timezone("America/New_York")
  try:
    xx= datetime.strptime(dt,"%Y-%m-%dT%H:%M:%SZ")
    result = pytz.utc.localize(xx, is_dst=None).astimezone(tz).replace(tzinfo=None)
  except:
    try:
        result= datetime.strptime(dt,"%Y-%m-%d %H:%M:%S")
    except:
        # Sat Jan 21 11:46:19 2017
        try:
            result= datetime.strptime(dt,"%a %b %d %H:%M:%S %Y")
        except:
            try:
                result= datetime.strptime(dt,"%Y-%m-%d")
            except:
                #2019-01-11 17:09:01.736307
                result= datetime.strptime(dt,"%Y-%m-%d %H:%M:%S.%f")
  return result

# From numberic level, get access. 
# Allow to set certian strings for specific levels
def accessLevelString(level,noaccess=None,user=None):
    try:
        level=int(level)
    except:
        return "??"+str(level)

    if (level==AccessByMember.LEVEL_USER) and user is not None:
        return user
    elif level == AccessByMember.LEVEL_NOACCESS:
        if noaccess is not None:
            return noaccess
        else:
            return "No Access"
    else:
        try:
            return AccessByMember.ACCESS_LEVEL[level]
        except:
            return "#"+str(level)
# resource is a DB model resource
def getResourcePrivs(resource=None,resourceid=None,member=None,resourcename=None,memberid=None):
    if resourcename:
        resource=Resource.query.filter(Resource.name==resourcename).one()
    elif resourceid:
        resource=Resource.query.filter(Resource.id==resourceid).one()
    if not member and not memberid:
        member=current_user
    p = AccessByMember.query.join(Resource,((Resource.id == resource.id) & (Resource.id == AccessByMember.resource_id))).join(Member,((AccessByMember.member_id == member.id) & (Member.id == member.id))).one_or_none()
    if p:
        level= p.level
    else:
        level = -1

    if (member and member.privs('HeadRM')):
        level=AccessByMember.LEVEL_ADMIN
    if member and member.active.lower() != "true": 
        level=0
    else:
        try:
            level=int(level)
        except:
            level=0

    levelText = accessLevelString(AccessByMember.ACCESS_LEVEL[level])

    return (level,levelText)

# LOG
# (Default)  "commit=1" to log and commit immediatley. THis will use a separate DB context as to
# not interfere with anything else.
# Use  "commit=0" will NOT commit. User MUST commit the default db.session to commit.
def log(eventtype=0,message=None,member=None,tool_id=None,member_id=None,resource_id=None,text=None,doneby=None,commit=1):
    logsess = db.session
    if commit:
        logsess = db.create_scoped_session(
        options=dict(bind=db.get_engine(g, 'logs'),
                     binds={}))
    if not member_id and member:
      member_id = member.id
    logsess.add(Logs(member_id=member_id,resource_id=resource_id,tool_id=tool_id,event_type=eventtype,doneby=doneby,message=message))
    if commit:
        logsess.commit()

# RULE - only call this from web APIs - not internal functions
# Reason: If we have calls or scripts that act on many records,
# we probably shouldn't generate a million messages
def kick_backend():
    try:
      gc= current_app.config['globalConfig']
      topic= gc.mqtt_base_topic+"/control/broadcast/acl/update"
      mqtt_pub.single(topic, "update", hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
    except BaseException as e:
        logging.debug("MQTT acl/update failed to publish: "+str(e))

# This is the one to allow a user temporary accces
def send_tool_unlock(toolname,member,node,level,code):
    try:
      gc= current_app.config['globalConfig']
      topic= gc.mqtt_base_topic+"/control/node/%s/allow" % (node)
      data = {'member':member.member,'member_id':member.id,'level':level,'code':code,'node':node,'tool':toolname}
      mqtt_pub.single(topic, json.dumps(data), hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
    except BaseException as e:
        logging.warning("MQTT acl/update failed to send tool open message: "+str(e))

# Send a "lockout" to a tool
def send_tool_lockout(toolname,node,reason):
    try:
      gc= current_app.config['globalConfig']
      topic= gc.mqtt_base_topic+"/control/node/%s/personality/lock" % (node)
      data = {'reason':reason,'tool':toolname}
      mqtt_pub.single(topic, json.dumps(data), retain=True, hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
    except BaseException as e:
        logging.warning("MQTT acl/update failed to send tool open message: "+str(e))

# Send a "removelockout" to a tool
def send_tool_remove_lockout(toolname,node):
    try:
      gc= current_app.config['globalConfig']

			# Remove the persistant "lock" messsage (retain=False)
      topic= gc.mqtt_base_topic+"/control/node/%s/personality/lock" % (node)
      mqtt_pub.single(topic,None, retain=False,hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)

			# Send the unlock message
      topic= gc.mqtt_base_topic+"/control/node/%s/personality/unlock" % (node)
      data = {'tool':toolname}
      mqtt_pub.single(topic, json.dumps(data), hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
    except BaseException as e:
        logging.warning("MQTT acl/update failed to send tool open message: "+str(e))
