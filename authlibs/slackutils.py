#!/usr/bin/python
"""
vim:tabstop=2:noexpandtab
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
import init
from db_models import db, ApiKey, Role, UserRoles, Member, Resource, MemberTag, AccessByMember, Blacklist, Waiver
from slackclient import SlackClient 
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response, Markup

from templateCommon import *

Config = init.get_config()
slack_token = Config.get('Slack','BOT_API_TOKEN')


def get_users():
    sc = SlackClient(slack_token)
    if sc.rtm_connect():
      sc.server.websocket.sock.setblocking(1)
      #print json.dumps(get_users(sc),indent=2)
      if sc.server.connected:
	users={}
	return sc.api_call("users.list")

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
    for m in db.session.query(Member).filter((Member.slack== None) | (Member.slack=="")).all():
        found=False
        total += 1
        if m.member.lower() in byuser:
            name+=1
            found=True
            m.slack = byuser[m.member.lower()]['name']

        if not found  and m.alt_email:
            if m.alt_email.lower() in byrawemail:
                altemail+=1
                m.slack = byrawemail[m.alt_email.lower()]['name']
                found=True

        if not found:
            if m.member.lower() in byemail:
                email+=1
                m.slack = byemail[m.member.lower()]['name']
                found=True

        #if not found:
        #    print "Missing",m.member
    
    db.session.commit()
    logger.info("Slack Member match Total %s name %s emails %d altemail %s unfound %s" %(total,name,email,altemail,(total-(name+email+altemail))))

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
            missing.append({'name':x,'email':users[x]['email']})
    logger.info( "SLACK DB: TOTAL"+str(len(users))+" FOUND IN MEMBERS: "+str(found)+" "+str(ORPHANS)+" "+str(len(missing)))
    #for x in missing:
    #    print "MSNG",x,users[x]['email']
    return missing

def get_unmatched_members():
    members =   Member.query.filter((Member.slack == "") | (Member.slack == None)).all()
    logger.debug( "Members without slack records: %s " % len(members))
    return members


def create_routes(app):
    @roles_required(['Admin','Useredit'])
    @app.route('/slack', methods=['GET','POST'])
    def slack_page():
        if "Undo" in request.form:
            m = Member.query.filter(Member.member==request.form['member_id']).one()
            m.slack=None
            db.session.commit()
            flash("Undone.")

        if "Link" in request.form:
            print request.form['member']
            print request.form['slack']
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
        automatch_missing_slack_ids()
        print "Slack"
        print  get_unmatched_slack_ids()
        print "Members`"
        print get_unmatched_members()
                


