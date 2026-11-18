#!/usr/bin/python
"""
vim:tabstop=2:expandtab:shiftwidth=2:softtabstop=2
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
from . import init
from .db_models import db, ApiKey, Role, UserRoles, Member, Resource, MemberTag, AccessByMember, Blacklist, Waiver
from slack_sdk import WebClient as SlackClient
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response, Markup

from .templateCommon import *

Config = init.get_config()
slack_token = Config.get('Slack','BOT_API_TOKEN')
slack_disabled =  Config.has_option('Slack','Disabled')


def get_users():
    sc = SlackClient(slack_token)
    #if sc.rtm_connect():
    #  sc.server.websocket.sock.setblocking(1)
    #print json.dumps(get_users(sc),indent=2)
    #if sc.server.connected:
    return sc.users_list()
    #else:
    #  logger.error("get_users slack connection fail")

def get_users_by_name(all_users=None):
  # Get a summarized, simplified recordeset
  # Indexed by username
  users={}
  if not all_users:
    all_users = get_users()
  for m in all_users['members']:
    p = m['profile']
    if not m['is_bot'] and not m['deleted']:
        if type(m['real_name']) == "set": m['real_name']=m['real_name'][0]
        if type(m['name']) == "set": m['name']=m['name'][0]
        if 'email' in p:
            idx = m['name'].lower()
            users[idx]={"realname":m['real_name'],"slack_id":m['id'],'name':m['name'],'email':p['email']}
  return users

def get_users_by_raw_email(all_users=None):
    # Get a summarized, simplified recordeset
    # Indexed by email address (in lowercase) for easy matching
    users={}
    if not all_users:
        all_users = get_users()
    for m in all_users['members']:
        p = m['profile']
        if not m['is_bot'] and not m['deleted']:
          if type(m['real_name']) == "set": m['real_name']=m['real_name'][0]
          if type(m['name']) == "set": m['name']=m['name'][0]
          if 'email' in p:
              idx = p['email'].lower()
              users[idx]={"realname":m['real_name'],"slack_id":m['id'],'name':m['name'],'email':p['email']}
    return users

def get_users_by_email(all_users=None):
  # Get a summarized, simplified recordeset
  # Indexed by email address (in lowercase) for easy matching
  users={}
  if not all_users:
      all_users = get_users()
  for m in all_users['members']:
    p = m['profile']
    if not m['is_bot'] and not m['deleted']:
      if type(m['real_name']) == "set": m['real_name']=m['real_name'][0]
      if type(m['name']) == "set": m['name']=m['name'][0]
      if 'email' in p:
        idx = p['email'].split("@")[0].lower()
        users[idx]={"realname":m['real_name'],"slack_id":m['id'],'name':m['name'],'email':p['email']}
  return users

# Automatic match for HIGH CONFIDENCE matches
def automatch_missing_slack_ids():
    total=0
    name=0
    email=0
    altemail=0
    slackdata= get_users()
    byuser  = get_users_by_name(slackdata)
    byemail = get_users_by_email(slackdata)
    byrawemail = get_users_by_raw_email(slackdata)
    q = db.session.query(Member)
    q = q.filter((Member.slack== None) | (Member.slack==""))
    for m in q.all():
        found=False
        total += 1
        if m.member.lower() in byuser:
            name+=1
            found=True
            m.slack = byuser[m.member.lower()]['slack_id']

        if not found  and m.alt_email:
            if m.alt_email.lower() in byrawemail:
                altemail+=1
                m.slack = byrawemail[m.alt_email.lower()]['slack_id']
                found=True

        if not found  and m.email:
            if m.email.lower() in byrawemail:
                altemail+=1
                m.slack = byrawemail[m.email.lower()]['slack_id']
                found=True

        if not found:
            if m.member.lower() in byemail:
                email+=1
                m.slack = byemail[m.member.lower()]['slack_id']
                found=True

        #if not found:
        #    print "Missing",m.member
    
    db.session.commit()
    logger.info("Slack Member match Total %s name %s emails %d altemail %s unfound %s" %(total,name,email,altemail,(total-(name+email+altemail))))
    return ("Slack Member match Total %s name %s emails %d altemail %s unfound %s" %(total,name,email,altemail,(total-(name+email+altemail))))

def get_unmatched_slack_ids():
    missing=[]
    found=0
    total=0
    users = get_users_by_name()
    for m in db.session.query(Member.slack).filter((Member.slack!= None) & (Member.slack!="")).all():
        total+=1
        if m.slack.lower() in users:
            found +=1
            users[m.slack.lower()]['found']=True
    #print "TOTAL MEMBERS",total,"FOUND IN SLACK",found
    found=0
    for x in users:
        if 'found' in users[x]: 
            found+=1
        else:
            missing.append({'name':x,'email':users[x]['email'],'slack_id':users[x]['slack_id']})
    #logger.info( "SLACK DB: TOTAL "+str(len(users))+" FOUND IN MEMBERS: "+str(found)+"  "+str(len(missing)))
    #for x in missing:
    #    print "MSNG",x,users[x]['email']
    return missing

def get_unmatched_members():
    members =   Member.query.filter((Member.slack == "") | (Member.slack == None)).all()
    #logger.debug( "Members without slack records: %s " % len(members))
    return members


def create_routes(app):
    @roles_required(['Admin','Finance','Useredit'])
    @app.route('/slack', methods=['GET','POST'])
    def slack_page():
        if "Undo" in request.form:
            m = Member.query.filter(Member.member==request.form['member_id']).one()
            m.slack=None
            db.session.commit()
            flash("Undone.")

        if "Update" in request.values:
            flash( automatch_missing_slack_ids())

        if "Link" in request.form:
            #print request.form['member']
            #print request.form['slack']
            if not current_user.privs('Useredit'):
                flash("No privilges to assign")
            else:
                m = Member.query.filter(Member.member==request.form['member']).one()
                m.slack = request.form['slack']
                db.session.commit()
                btn = '''<form method="POST">
                        <input type="hidden" name="member_id" value="%s" />
                        <input type="submit" value="Undo" name="Undo" />
                        </form>''' % (m.member)
                flash(Markup("{0} assinged slack ID {1} {2}".format(m.member,m.slack,btn)))
        try:
          slacks=get_unmatched_slack_ids()
          members=get_unmatched_members()
        except BaseException as e:
          logger.error("Failed to contact slack %s"%(str(e)))
          flash("Could not reach slack. Communication or configuration error","warning")
          slacks=[]
          members={}
        return render_template('slack.html',slacks=slacks,members=members)

def cli_slack(cmd,**kwargs):
        db.session.query(Member).all()
        print ("Automatching missing IDs")
        print (automatch_missing_slack_ids())
        #print "\n\nSlack"
        #print  get_unmatched_slack_ids()
        #print "\n\nMembers"
        #print get_unmatched_members()
        #print "\n\nall users"
        print (get_users())


def send_slack_message(towho,message):
  sc = SlackClient(slack_token)
  #if sc.rtm_connect():
  #  print "SLACK-SEND",towho,message
  for chan in towho.split(","):
    try:
      #cid = get_channel_id(sc,chan.replace("#",""))
      #if not cid:
      #  logger.error("ID for channel {0} not found".format(chan))
      #  continue
      # Bot can't invite users to channels it doesn't belong to
      #res = api_call_ratelimit(sc,
      #  "conversations.join",
      #  channel=cid
      #  )

      #res = sc.chat_postMessage(
      #    channel=chan.replace("#",""),
      #    text=message
      #    )

      res = sc.api_call(
        "chat.postMessage",
        json = {
            'channel':chan,
            'text':message
        }
      )
    except BaseException as e:
        logger.error(f"Error posting Slack channel \"{chan}\": {e}")

def get_channel_id(sc,channel):
  channel = channel.strip().lower()
  if channel[0] == "#": channel = channel[1:]
  next_cursor=None
  while True:
    res = sc.conversations_list(
        cursor=next_cursor,
        exclude_archived=True
      )
    if not res['ok'] and res['error'] == 'ratelimit':
      time.sleep(2)
      continue
    d = None
    for x in res['channels']:
      #if x['is_channel']: print channel,x['name']
      if channel == x['name'].lower() and x['is_channel']:
        d = x['id']
        return d
    if 'response_metadata' not in res or 'next_cursor' not in res['response_metadata']:
      break
    next_cursor = res['response_metadata']['next_cursor']
    if next_cursor.strip() == "": break
  return d

def cli_slack_add_all_to_channels(cmd,**kwargs):
  print ("Adding everytone to their user channels (This takes a while..)")
  members = db.session.query(Member).all()
  resources = db.session.query(Resource).all()
  sc = SlackClient(slack_token)
  if sc:
    for r in resources:
      if r.slack_chan:
        cid = get_channel_id(sc,r.slack_chan)
        print (r," uses ",r.slack_chan,cid)
        if not cid:
          logger.warning("{1} resource Slack channel {0} does not exist".format(r.slack_chan,r.short))
        else:
          # Can't add if we're not a member
          res = api_call_ratelimit(sc,
            "conversations.join",
            channel=cid
            )
          if not res['ok']:
            logger.error("Error addming myself to slack channel {1}: {2}".format(channel,res['error']))

          mm = AccessByMember.query.filter(AccessByMember.resource_id == r.id)
          mm = mm.outerjoin(Member,(AccessByMember.member_id == Member.id))
          mm = mm.add_column(Member.member)
          mm = mm.add_column(Member.id)
          mm = mm.add_column(Member.slack)
          for (acc,member,dd,slack) in mm.all():
            print (acc,member,dd,slack)
            if dd:
              if slack_disabled:
                logger.error("SLACK DISABLED inviting {0} to slack channel {1}: {2}".format(member,r.slack_chan,res['error']))
              else:
                res = api_call_ratelimit(
                      sc,
                      "conversations.invite",
                      channel=cid,
                      users=dd
                      )
                if not res['ok']:
                  logger.error("Error inviting {0} to slack channel {1}  {2}".format(member,r.slack_chan,res['error']))
                

def api_call_ratelimit(sc,api,**kwargs):
  while True:
    x = sc.api_call(api_method=api,json=kwargs)
    if x['ok'] or x['error'] != "ratelimit":
      return x
    time.sleep(1)
      
    
def add_user_to_channel(channel,member):
  if not member.slack:
    return False
  sc = SlackClient(slack_token)
  if sc:
    cid = get_channel_id(sc,channel)
    if not cid:
      logger.error("ID for channel {0} not found".format(channel))
      return False
    # Bot can't invite users to channels it doesn't belong to
    res = api_call_ratelimit(sc,
      "conversations.join",
      channel=cid
      )
    if slack_disabled:
        logger.warning("SLack is Disabled")
    else:
      try:
        res = api_call_ratelimit(
              sc,
              "conversations.invite",
              channel=cid,
              users=member.slack
              )
        if not res['ok']:
          logger.error("Error Inviting {0} to slack channel {1}  {2}".format(member.member,channel,res['error']))
        return False
      except BaseException as e:
          logger.error("Error Inviting {0} to slack channel {1}  {2}".format(member.member,channel,e))
          return False

    
  return True


def cli_slacktest(cmd,**kwargs):
    m = Member.query.filter(Member.id==13).one()
    send_slack_message(m.slack,"test")

