#!/usr/bin/python
# vim:tabstop=2:shiftwidth=2:expandtab

"""
Get from: https://www.digicert.com/CACerts/DigiCertGlobalRootCA.crt
export WEBSOCKET_CLIENT_CA_BUNDLE=DigiCertGlobalRootCA.crt

If your SlackClient is old, you might need to modify it with:

import logging
logger = logging.getLogger('websockets.server')
logger.setLevel(logging.ERROR)
logger.addHandler(logging.StreamHandler())

(If you see a logger error loading it - this is the fix)

"""

import os,time,json,datetime,sys
import linecache
from authlibs import init
import requests,urllib,urllib2
from  authlibs import config
from authlibs.init import authbackend_init, get_config, createDefaultUsers
from authlibs import cli
from authlibs import utilities as authutil
import argparse

import logging
logger = logging.getLogger(__name__)
streamHandler = logging.StreamHandler()
streamHandler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - SLACKBOT - %(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)

api_username = config.Config.get("Slack","SLACKBOT_API_USERNAME")
api_password = config.Config.get("Slack","SLACKBOT_API_PASSWORD")
slack_logfile = config.Config.get("Slack","LOGFILE")
url_base = config.Config.get("backups","localurl")

log_events=[]
logger.addHandler(streamHandler)

from authlibs.templateCommon import *

parser=argparse.ArgumentParser()
parser.add_argument("--lockout","-l",help="Lockout <message>")
parser.add_argument("--unlock","-u",help="Unlock <message used for lock>")
parser.add_argument("--check","-c",help="Check <message used for lock>")
parser.add_argument("--dryrun","-",help="Do not do - just show",action="store_true")

(args,extras) = parser.parse_known_args(sys.argv[1:])
app=authbackend_init(__name__)
with app.app_context():
  Config = init.get_config()

  roles=Role.query.all()
  admins =Member.query.join(UserRoles,UserRoles.member_id == Member.id).join(Role,Role.id == UserRoles.role_id)
  admins = admins.add_column(Role.name).group_by(Member.member).all()
  roles=[]
  for x in admins:
      roles.append({'member':x[0],'role':x[1]})

  privs=AccessByMember.query.filter(AccessByMember.level>0).join(Member,Member.id==AccessByMember.member_id)
  privs = privs.join(Resource,Resource.id == AccessByMember.resource_id)
  privs = privs.add_columns(Resource.name,AccessByMember.level,Member.member,Member.id)
  privs = privs.all()
  p=[]
  immune_ids= []
  immune_members= {}
  for x in privs:
      p.append({'member_id':x[4],'member':x[3],'resource':x[1],'priv':AccessByMember.ACCESS_LEVEL[int(x[2])]})
      immune_ids.append(x[4])
      immune_members[x[4]]=x[3]

  did = Resource.query.filter(Resource.name=="frontdoor").one().id
  count=0
  q= AccessByMember.query.filter(AccessByMember.resource_id==1).join(Member,Member.id==AccessByMember.member_id)
  q = q.add_column(Member.member)
  for (a,mem) in q.all():
    if a.member_id in immune_ids:
      print "IMMUNE",immune_members[a.member_id],mem
    elif args.lockout:
        if a.lockout_reason and a.lockout_reason!="":
          print "Already Locked out",mem,"becasue",a.lockout_reason
        else:
          count+=1
          a.active = 0
          a.lockout_reason = args.lockout
    elif args.unlock:
        if a.lockout_reason and a.lockout_reason.strip() != args.unlock.strip():
          print "Locked out",mem,"different reason",a.lockout_reason
        elif a.lockout_reason and a.lockout_reason.strip() == args.unlock.strip():
          count+=1
          a.lockout_reason = None
        else:
          print "was unlocked",mem
    elif args.check:
        if a.lockout_reason and a.lockout_reason.strip() != args.check.strip():
          print "Locked out",mem,"for different reason",a.lockout_reason
        elif a.lockout_reason and a.lockout_reason.strip() == args.check.strip():
          count+=1
        else:
          print "Member has access",mem
  print "Records",count
  #print "DID",did
  if not args.dryrun:
    authutil.kick_backend()
    db.session.commit()
  
  
#print immune_members

