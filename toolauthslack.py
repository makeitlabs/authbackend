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

import logging
logger = logging.getLogger(__name__)
streamHandler = logging.StreamHandler()
streamHandler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - SLACKBOT - %(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)

api_username = config.Config.get("Slack","SLACKBOT_API_USERNAME")
api_password = config.Config.get("Slack","SLACKBOT_API_PASSWORD")

log_events=[]
logger.addHandler(streamHandler)

from authlibs.templateCommon import *

logger.info("Files copied")
print "LOAD"
from slackclient import SlackClient
print "DONE"

Config = init.get_config()
slack_token = Config.get('Slack','BOT_API_TOKEN')
sc = SlackClient(slack_token)

def oxfordlist(lst,conjunction="or"):
	text=""
	if len(lst)==0:
		return ""
	if len(lst)==1:
		return(lst[0])
	text = ", ".join(lst[:-1])
	text += " "+conjunction+" "+lst[-1]
	return text

def get_users(sc):
	users={}
	all_users = sc.api_call("users.list")
	#print json.dumps(all_users,indent=2)
	for m in all_users['members']:
		p = m['profile']
		if not m['is_bot'] and not m['deleted']:
			if type(m['real_name']) == "set": m['real_name']=m['real_name'][0]
			if type(m['name']) == "set": m['name']=m['name'][0]
			#print type(m['real_name']),type(m['name']),type(m['id'])
			users[m['name']]={"name":m['real_name'],"slack_id":m['id']}

	return users

def matchusers(sc,user,ctx,pattern):
  matches=[]
	v=""

	if 'quids' not in ctx:
		ctx['quids']={}

  foundQuick=False
  if 'quids' in ctx:
    for q in ctx['quids']:
      if q==pattern:
        u=ctx['quids'][q]
        matches.append(u)
        v += ("{1} {2} {0:s}\n".format(u['name'],q,u['member']))
        return (matches,v)

  if not foundQuick:
    req = requests.Session()
    url = "http://127.0.0.1:5000/api/membersearch/"+safestr(pattern)
    r = req.get(url, auth=(api_username,api_password))
    if r.status_code != 200:
      raise BaseException ("%s API failed %d" % (url,r.status_code))
    members=r.json()
    for x in members:
        # Add to quid list
        for q in range(0,99):
          f= "{0:02d}".format(q)
          if f not in ctx['quids']: break
        
        inQ=False
        for q in ctx['quids']:
          if x['id'] == ctx['quids'][q]['id']: 
            inQ=True
            v += ("{1} {2} {0:s}\n".format(x['title'],q,x['member']))
    
        if not inQ:
          ctx['quids'][f]={'name':x['title'],'member':x['member'],'id':x['id']}
          v += ("{1} {2} {0:s}\n".format(x['title'],f,x['member']))

        matches.append({'name':x['title'],'member':x['member'],'id':x['id']})
	return (matches,v)

def cancel_callbacks(ctx):
	if 'confirm_callback' in ctx: del ctx['confirm_callback']
	if 'cancel_callback' in ctx: del ctx['cancel_callback']

def authorize_confirm(sc,user,ctx):
  req = requests.Session()
  url = "http://127.0.0.1:5000/api/v1/authorize"
  data={'slack_id': user['user']['profile']['display_name']}
  data['resources']=[r['id'] for r in ctx['authorize_resources']]
  data['members']=[m['id'] for m in ctx['authorize_users']]
  data['level']=0
  r = req.post(url, json=data,auth=(api_username,api_password))
  if r.status_code == 400:
    t=r.json()
    return "Failed: %s" % t['reason']
  elif r.status_code != 200:
    raise BaseException ("%s API failed %d" % (url,r.status_code))

	cancel_callbacks(ctx)
	text = "Authorized "+oxfordlist([x['name'] for x in ctx['authorize_users']],conjunction="and")+" on "+oxfordlist([x['name'] for x in ctx['authorize_resources']],conjunction="and")+"."
	return text

def resources(sc,user,ctx,*s):
  text="*Resources*:\n"
  for r in get_resources():
    if r['short']:
      text += "%s (or \"%s\")\n" % (r['name'],r['short'])
    else:
      text += "%s\n" % (r['name'])
  return text
    
def on_resource(sc,user,ctx,*s):
	if 'authorize_users' not in ctx:
		return "Use the \"authorize\" command to say who you're trying to authorize, first"
  allresources=get_resources()
  resources=[]
	for r in s[1:]:
    for rr in allresources:
      if (r.lower() == rr['name'].lower()) or (rr['short'] is not None  and r.lower() == rr['short'].lower()):
        resources.append(rr)

	if len(resources) == 0:
		return "Authorize on what resource? (Type \"on <resources...>\""
	text = "Authorize "+oxfordlist([x['name'] for x in ctx['authorize_users']],conjunction="and")+" on "+oxfordlist([r['name'] for r in resources],conjunction="and")+"? Type \"ok\" to confirm"
	ctx['confirm_callback']=authorize_confirm
	ctx['authorize_resources']=resources
	return text
	
	

def authorize(sc,user,ctx,*s):
	error=""
	if len(s) <2:
		return "`USAGE: authorize <usersids..> [on <resources...>]`"
		
	res=False
	users=[]
	resourcenames=[]
	for x in s[1:]:
		if x.lower() == "on":
			res=True
		elif res == False:
			users.append(x)
		else:
			resourcenames.append(x)
	
	mems=[]
	for uid in users:

    if len(uid)>=2:
      (matches,cleartext) = matchusers(sc,user,ctx,uid)
    else:
      matches=[]
      error+=uid+" is not a valid userid. "
    if len(matches)>1:
      error+="Did you mean one of:\n```\n"+cleartext+"\n```\n"
      return error
    if len(matches)==1:
      mems.append(matches[0])

  allresources=get_resources()
  resources=[]
	for r in resourcenames:
    for rr in allresources:
      if (r.lower() == rr['name'].lower()) or (rr['short'] is not None  and r.lower() == rr['short'].lower()):
        resources.append(rr)
	
	if error != "":
		return error+"\n(Correct, or select from above list and try again)"

	if (len(mems)==0):
		return "You must specify users to authorized on"
	ctx['authorize_users']=mems
	if (len(resources)==0):
		return "Authorize "+oxfordlist([m['name'] for m in mems],conjunction="and")+" on what resource? (Type \"on <resources...>\")"
	text = "Authorize "+oxfordlist([m['name'] for m in mems],conjunction="and")+" on "+oxfordlist([r['name'] for r in resources],conjunction="and")+"? Type \"ok\" to confirm"
	ctx['confirm_callback']=authorize_confirm
	ctx['authorize_resources']=resources
	return text

	return "DOne"
def divzero(sc,user,ctx,*s):
	x = 0/0
	return "Tadah!"

def echo_cmd(sc,user,ctx,*s):
	print "echo"," ".join([x for x in s])
	return "Echoed"

def safestr(s):
  """Sanitize input strings used in some operations"""
  keepcharacters = r"~|!@#$%^_-+=[]{};:.,><?"
  return "".join(c for c in s if c.isalnum() or c in keepcharacters).strip()

def get_resources():
  resources=[]
  req = requests.Session()
  url = "http://127.0.0.1:5000/api/v1/resources"
  r = req.get(url, auth=(api_username,api_password))
  if r.status_code != 200:
    raise BaseException ("%s API failed %d" % (url,r.status_code))
  res=json.loads(r.text)
  for x in res:
    resources.append({'id':x['id'],'short':x['short'],'name':x['name']})
  return resources

def api_cmd(sc,user,ctx,*s):
  result="```"
  if len(s)<2:
    return "No string specified"
	(matches,v)= matchusers(sc,user,ctx,s[1])
  result +=v
  result +=  "\nReturned %d match.\n" % len(matches)
  result += "```"
  return result

def tools_cmd(sc,user,ctx,*s):
  myid = safestr(user['user']['profile']['display_name'])
  req = requests.Session()
  url = "http://127.0.0.1:5000/api/v1/slack/tools/"+str(myid)
  r = req.get(url, auth=(api_username,api_password))
  if r.status_code != 200:
    raise BaseException ("%s API failed %d" % (url,r.status_code))
  else:
    return r.text

def use_tool(sc,user,ctx,*s):
  myid = safestr(user['user']['profile']['display_name'])
  if (len(s)<2):
    print "Which tool or resource?"
  tool = s[1]
  req = requests.Session()
  url = "http://127.0.0.1:5000/api/v1/slack/open/"+tool+"/"+str(myid)
  r = req.get(url, auth=(api_username,api_password))
  if r.status_code != 200:
    raise BaseException ("%s API failed %d" % (url,r.status_code))
  else:
    return r.text

def whoami(sc,user,ctx,*s):
  myid = safestr(user['user']['profile']['display_name'])
  req = requests.Session()
  url = "http://127.0.0.1:5000/api/v1/slack/whoami/"+str(myid)
  r = req.get(url, auth=(api_username,api_password))
  if r.status_code != 200:
    raise BaseException ("%s API failed %d" % (url,r.status_code))
  else:
    return r.text

def admin_commands(sc,user,ctx,*s):
  myid = safestr(user['user']['profile']['display_name'])
  req = requests.Session()
  url = "http://127.0.0.1:5000/api/v1/slack/admin/"+str(myid)
  data= {'command':s[1:]}
  r = req.post(url, json=data,auth=(api_username,api_password))
  if r.status_code != 200:
    raise BaseException ("%s API failed %d" % (url,r.status_code))
  else:
    return r.text

def privileges(sc,user,ctx,*s):
  if len(s)<2:
    return "No user specified"
	(matches,v)= matchusers(sc,user,ctx,s[1])
  if (len(matches) == 0):
    return "No valid user found"
  if (len(matches) > 1):
    return "```Ambiguous - chose among:\n"+v+"```"

  req = requests.Session()
  url = "http://127.0.0.1:5000/api/v1/memberprivs/"+str(matches[0]['id'])
  r = req.get(url, auth=(api_username,api_password))
  if r.status_code != 200:
    raise BaseException ("%s API failed %d" % (url,r.status_code))
  privs=r.json()
  result =  matches[0]['name']+" has privileges on:\n"
  for p in privs:
    result += p['resource']
    if p['level'] != 'User':
      result += " (%s)" % p['level']
    result += "\n"
  return result


def quickids(sc,user,ctx,*s):
	if 'quids' not in ctx:
		return "No IDs cached"

	text=""
	for q in sorted(ctx['quids']):
      text += ("{0} {1} {2}\n".format(q,ctx['quids'][q]['member'],ctx['quids'][q]['name']))
	return "```"+text+"```"
		

def default_cancel_callback (sc,user,ctx):
	del ctx['cancel_callback']
	return "Canceled"

def clear_cmd(sc,user,ctx,*s):
  ctx['quids']={}

def cancel(sc,user,ctx,*s):
	if 'cancel_callback' not in ctx:
		return "Nothing pending to cancel"
	return ctx['cancel_callback'](sc,user,ctx)

def confirm(sc,user,ctx,*s):
	if 'confirm_callback' not in ctx:
		return "Nothing pending to confirm"

	return ctx['confirm_callback'](sc,user,ctx)

def userid(sc,user,ctx,*s):
	if len(s)!=2:
		return "USAGE: userid <patternid>"
	(matches,v)= matchusers(sc,user,ctx,s[1])
	if v=="":
		return "None Found :white_frowning_face:"
	else:
		return "```"+v+"```"

def show_event_log(sc,user,ctx,*s):
	global log_events
	text="```"
	for x in log_events:
		text += x+"\n"
	text+="```"
	return text
	
def ping(sc,user,ctx,*s):
	display_name=user['user']['profile']['display_name']
	return "Hello "+str(display_name)+" I am alive at "+str(datetime.datetime.now())

def help_cb(sc,user,ctx,*s):
	text = '```'
	if (len(s) == 2):
		text="```Unrecognized command. Type `help` for a list of commands"
		for x in verbs:
			if s[1].lower()==x['name'].lower():
				text = "*"+x['name']+"*\n```"
				if 'usage' in x:
					text += "Usage: "+x['usage']+"\n"
				if 'detail' in x:
					text += x['detail']+"\n\n"
				elif 'desc' in x:
					text += x['desc']+"\n\n"
	else:
		text= "Enter one of the following, or `help {command}` for more detail:\n```"

		for x in sorted(verbs,key=lambda x:x['name']):
			if 'callback' in x and 'hidden' not in x:
				if 'usage' in x:
					text += x['usage']+ "  -- "+x['desc']+"\n"
				elif 'desc' in x:
					text += x['name']+" - "+x['desc']+"\n"
				else:
					text += x['name'] +"\n"

		text+= "\nOther help topics:\n"
		for x in sorted(verbs,key=lambda x:x['name']):
			if 'callback' not in x and 'hidden' not in x:
				if 'desc' in x:
					text += x['name'] + " - "+x['desc']+"\n"
				else:
					text += x['name']
	text += '```'
	return text
	
# Dont specify a callback to just create a help topic

# usage is the command line - not used for help topics
# desc is SHORT info - MANDIRORY  quick description
# detail is the LONG detain (optional)

verbs = [
	{	'name':"authorize", 
		'callback':authorize,
		'usage':"authorize <userids...> [on <resrouces..>]",
		'desc':"Authorize a user to use a tool/resource",
		'detail':"Authorize one or more users on one or more resources. Specify user ids (or quick IDs) from \"userid\" command. Will try to match a user name, but if there is any ambiguity, it will fail (create quick IDs for possible matches) - and require you to retry. If you don't specify the resources, you'll have to afterwards."
	},
	{	'name':"userid", 
		'callback':userid,
		'usage':"userid <pattern>",
		'desc':"Find user's ID",
		'detail':"Search for a user's ID by specifying a portion of it - like \"Jo\" to find \"Joe\", \"Jon\", \"John\", etc. Command will return a list of matching users, their IDs, and temporary \"quick IDs\" that can be used to reduce keystrokes like \"01\""
	},
	{	'name':"resources", 
		'callback':resources,
		'usage':"resources",
		'desc':"List all resources"
	},
	{	'name':"divzero", 
		'callback':divzero,
		'desc':"Divide a number by zero"
	},
	{	'name':"divzero2", 
		'callback':divzero,
		'usage':"divzero",
		'desc':"Divide a number by zero"
	},
	{	'name':"divthree", 
		'callback':divzero,
		'desc':"Divide a number by zero"
	},
	{	'name':"quickid", 
		'callback':quickids,
		'desc':"Show quickids",
		'detail':"QuickIDs are TEMPORARY user ids used to make you need to type less. They are aways in the form of \"00\" (two digits). They are automatcally created by commands such as \"userid\" and \"authorize\" which lookup ids based on partial matches. Use them whenever user IDs are required. The \"quickid\" command will show you what is in your cache. These are short lived, and will always disappear shortly after used."
	},
	{	'name':"log", 
		'callback':show_event_log,
		'desc':"Show slackbot command log"
	},
	{	'name':"ping", 
		'callback':ping,
		'desc':"Just see if I'm alive"
	},
	{	'name':"confirm", 
		'callback':confirm,
		'desc':"Confirm a request",
		'detail':'When do tell me to do something - I will verify the request and ask you to confirm it. Type \"confirm\" or \"yes\" or \"ok\" to do it',
		'aliases':['ok','yes']
	},
	{	'name':"cancel", 
		'callback':cancel,
		'desc':"cancel a request",
		'detail':'When do tell me to do something - I will verify the request and ask you to confirm it. This is one way to explicitly cancel it',
		'aliases':['no']
	},
	{	'name':"user", 
		'desc':"email or slack id",
		'detail':"A slack or email id in the format of firstname.lastname, or a \"quick id\" as returned from the \"userid\" command like \"01\". Use \"userid\" command to help find a user's ID"
	},
	{	'name':"tools", 
		'desc':"tools - Show tools you have access to",
		'callback':tools_cmd,
	},
	{	'name':"api", 
		'desc':"api test",
		'callback':api_cmd,
		'detail':"Test of API calls"
	},
	{	'name':"on", 
		'callback':on_resource,
		'desc':"Say what resources you are authorizing users on",
		'detail':"this is the second-half of a sequence you would have started with the \"authorize\" command"
	},
	{
		'name':"resource", 
		"desc":"Tool or resoruce",
		'detail':"Short name/id of a tool or resource, like \"laser\" or \"lift\". Use \"resources\" command to see a list"
	},
	{
		'name':"privileges", 
		'callback':privileges,
		"desc":"privileges {member}",
		'detail':"See resource privileges for a user"
	},
	{
		'name':"echo", 
		'callback':echo_cmd,
		"desc":"Echo to console",
		'detail':"Echo string to console - for debug"
	},
	{
		'name':"clear", 
		'callback':clear_cmd,
		"desc":"clear - Clear Quick ID Cache"
	},
	{
		'name':"open", 
		'callback':use_tool,
		"desc":"open {resource}  - Request RFID-less access to a tool or specific resource"
	},
	{
		'name':"use", 
		'callback':use_tool,
		"desc":"use {resource}  - Request RFID-less access to a tool or specific resource"
	},
	{
		'name':"whoami", 
		'callback':whoami,
		"desc":"whoami - ID youself - diagnostic"
	},
	{
		'name':"admin", 
		'callback':admin_commands,
		"hidden":True
	},
	{'name':"help", 'callback':help_cb,'aliases':['?']}
]

def prune_contexts(contexts):
	now=datetime.datetime.now()
	d=[]
	for x in contexts:
		ctx=contexts[x]
		#print x,now-ctx['lastUsed']
		if ((now-ctx['lastUsed']) > datetime.timedelta(minutes=15)):
			d.append(x)
	for x in d:
		print "DELETE CONTEXT",x
		del contexts[x]

def log_event(name,message):
	global log_events
	logstr=str(datetime.datetime.now())+" "+name+" "+message
	log_events.append(logstr)
	print logstr
	open("slackbot.log","a").write(logstr+"\n")
	if len(log_events)>40:
		log_events=log_events[1:]
	

keepgoing=True


while keepgoing:
	log_event("<system>","Reconnect")
	if sc.rtm_connect():
		sc.server.websocket.sock.setblocking(1)
		contexts={}
		#print json.dumps(get_users(sc),indent=2)
		all_users = sc.api_call("users.setPresence",presence="active")
		while sc.server.connected is True and keepgoing is True:
			try:
				l= sc.rtm_read()
			except KeyboardInterrupt:
				log_event("<System>", "Keyboard Interrupt")
				keepgoing=False
				sys.exit(0)
			except BaseException as e:
				log_event("<Exception>", str(e))
				break
			#print "READ",l
			for msg in l:
				if 'type' in msg and (msg['type'] == "message"):
					try:
						text="???"
						#print "Message from ",msg['user'],msg['text'],msg['channel']
						chan = msg['channel']
						if chan not in contexts:
							contexts[chan]={}
						contexts[chan]['lastUsed']=datetime.datetime.now()
						userinfo= sc.api_call("users.info",user=msg['user'])
						#print json.dumps(userinfo,indent=2)
						display_name=userinfo['user']['profile']['display_name']
						display_name_norm=userinfo['user']['profile']['display_name_normalized']
						email=userinfo['user']['profile']['email']
						#print json.dumps(msg,indent=2)
						m = msg['text'].strip().replace("\s+"," ").split()
						if len(m)==0:
							m=[""]
						matches=[]
						cb=None
						exact=None
						for v in verbs:
							#if (m[0].lower().startswith(v['name'].lower())) and 'callback' in v: 	
							cmds=[v['name'].lower()]
							if 'aliases' in v:
								for a in v['aliases']: cmds.append(a.lower())
							for cmd in cmds:
								if (cmd.startswith(m[0].lower())) and 'callback' in v: 	
									matches.append(v['name'])
									cb=v['callback']
									if m[0].lower() == v['name'].lower():
										exact=cb
									
						if exact:
							log_event( display_name,msg['text'])
							text=exact(sc,userinfo,contexts[chan],*m)
						elif len(matches)==1:
							log_event( display_name,msg['text'])
							text=cb(sc,userinfo,contexts[chan],*m)
						elif len(matches)==0:
							text="Unknown command. Type `help` for help"
						else: 
							text="Ambiguous command: Did you mean "
							text += oxfordlist(matches)
							text += "?\n(`help` for more)"
						
					except BaseException as e:
						text = ":alert: Epic fail: ```"+str(e)+"```"
						log_event( "<Error>",str(e))

					sc.rtm_send_message(msg['channel'],text)
			prune_contexts(contexts)
			sys.stdout.flush()
	else:
		print "Connection Failed"
	time.sleep(2)
	print "RETRY"

