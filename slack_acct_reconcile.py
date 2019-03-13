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
from slackclient import SlackClient

import logging
logger = logging.getLogger(__name__)
streamHandler = logging.StreamHandler()
streamHandler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - SLACKBOT - %(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)

Config = init.get_config()
api_username = Config.get("Slack","SLACKBOT_API_USERNAME")
api_password = Config.get("Slack","SLACKBOT_API_PASSWORD")
slack_logfile = Config.get("Slack","LOGFILE")
url_base = Config.get("backups","localurl")

log_events=[]
logger.addHandler(streamHandler)

from authlibs.templateCommon import *
from authlibs.init import authbackend_init

def get_users(sc):
	users={}
	all_users = sc.api_call("users.list")
	#print json.dumps(all_users,indent=2)
	for m in all_users['members']:
    #print json.dumps(m,indent=2)
		p = m['profile']
		if not m['is_bot'] and not m['deleted'] and 'email' in p:
			if type(m['real_name']) == "set": m['real_name']=m['real_name'][0]
			if type(m['name']) == "set": m['name']=m['name'][0]
			#print type(m['real_name']),type(m['name']),type(m['id'])
			users[m['name']]={"name":m['real_name'],"slack_id":m['id'],'email':p['email']}
	return users


if __name__ == "__main__":
  slack_token = Config.get('Slack','BOT_API_TOKEN')
  sc = SlackClient(slack_token)
	if sc.rtm_connect():
		#sc.server.websocket.sock.setblocking(1)
		if sc.server.connected:
      users = get_users(sc)
      #print json.dumps(users,indent=2)
      print "Got",len(users),"Users"
      app=authbackend_init(__name__)
      with app.app_context():
        match=0
        nomatch=0
        multiple=0
        for u in users:
          usr=users[u]
          m = Member.query.filter(Member.email.ilike(usr['email'])).all()
          if len(m)>1:
            print "MULTIPLE MATCHES for ",u,usr['email']
            multiple+=1
          if len(m)==1:
            if u != m[0].slack:
              print "CHANGE",m[0].slack,"NOW",usr['name'],usr['slack_id'],u
            m[0].slack = usr['slack_id']
            match+=1
          else:
            print "NO MATCH for ",u,usr['email']
            nomatch+=1
        db.session.commit()
      print "Multiple",multiple,"Match",match,"No-Match",nomatch,"Total",(match+nomatch+multiple)

      

