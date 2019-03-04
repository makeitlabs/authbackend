#!/usr/bin/python

import sys,re,os,urllib2,urllib,requests
from  datetime import datetime,timedelta
import json
import ConfigParser
from slackclient import SlackClient


now = datetime.now()
yesterday = now-timedelta(days=1)
todaystr = now.strftime("%Y-%m-%d")
yesterdaystr = yesterday.strftime("%Y-%m-%d")

Config = ConfigParser.ConfigParser({})
Config.read('makeit.ini')
slack_token = Config.get('backups','BOT_API_TOKEN')
api_username = Config.get("backups","api_username")
api_password = Config.get("backups","api_password")
ACL_STORAGE = Config.get("backups","acl_backup_directory")
BASE= Config.get("backups","localurl")
api_creds = (api_username,api_password)
sc = SlackClient(slack_token)

sc.rtm_connect()
sc.server.websocket.sock.setblocking(1)

def compare_v1(first,second,resource):
	str=""
	fn1 = "%s/%s-%s-v1.txt" % (ACL_STORAGE,first,resource)
	fn2 = "%s/%s-%s-v1.txt" % (ACL_STORAGE,second,resource)
	f1 = json.load(open(fn1))
	f2 = json.load(open(fn2))

	f={}
	for x in f1:
		if x['allowed'] == 'false': x['allowed'] = 'denied'
		f[x['member']] = x

	s={}
	for x in f2:
		if x['allowed'] == 'false': x['allowed'] = 'denied'
		s[x['member']] = x

	for x in f:
		if x not in s:
			str += "%s removed - was %s\n`%s`\n\n"% (x,f[x]['allowed'],f[x]['warning'])
		else:
			if f[x]['allowed'] != s[x]['allowed']:
				str += "%s was %s, now %s\n`%s`\n\n" % (x,f[x]['allowed'],s[x]['allowed'],s[x]['warning'])

	for x in s:
		if x not in f:
			str += "%s added - %s\n`%s`\n\n"% (x,s[x]['allowed'],s[x]['warning'])

	
	return str

def get_v0_acl(resource):
	req = requests.Session()
	url = BASE+"/api/v0/resources/%s/acl" % resource
	r = req.get(url, auth=api_creds)
	if r.status_code != 200:
		raise BaseException ("%s API failed %d" % (url,r.status_code))
	fn = "%s/%s-%s-v0.txt" % (ACL_STORAGE,todaystr,resource)
	open(fn,"w").write(r.text)

def get_v1_acl(resource):
	req = requests.Session()
	url = BASE+"/api/v1/resources/%s/acl" % resource
	r = req.get(url, auth=api_creds)
	if r.status_code != 200:
		raise BaseException ("%s API failed %d" % (url,r.status_code))
	fn = "%s/%s-%s-v1.txt" % (ACL_STORAGE,todaystr,resource)
	open(fn,"w").write(r.text)

def do_update():
	req = requests.Session()
	url = BASE+"/api/v1/resources"
	r = req.get(url, auth=api_creds)
	if r.status_code != 200:
		raise BaseException ("%s API failed %d" % (url,r.status_code))

	for x in r.json():
		get_v0_acl(x['name'])
		get_v1_acl(x['name'])
		str= compare_v1(yesterdaystr,todaystr,x['name'])
		if x['slack_admin_chan']:
			sc.api_call(
				"chat.postMessage",
				channel=x['slack_admin_chan'],
				text=str
				)

if __name__ == "__main__":
	do_update()

