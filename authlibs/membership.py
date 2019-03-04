#!/usr/bin/env python
#vim:tabstop=2:expandtab
# Membership-related functions, to decouple from UI

import config
import dbutil
import utilities
import random
from collections import defaultdict
import config
import sys
import argparse
from db_models import db, Subscription, Member, Blacklist, Logs
import ConfigParser
import eventtypes
from datetime import datetime
from flask import current_app

from templateCommon import *

import google_admin as google
from authlibs import accesslib

def syncWithSubscriptions(isTest=False):
  '''Use the latest Subscription data to ensure Membership list is up to date'''
  logger.debug("Get Missing Members")
  missing = getMissingMembers()

  ''' Try to match subscriptions to existing member records - TODO - "new/update" flag '''
  logger.debug("match missing members")
  newMembers = matchMissingMembers(missing)

  ''' Create new member records for actual new members '''
  logger.debug("ADDING MISSING MEMBERS")
  added=addMissingMembers(newMembers)

  ''' Create Google (someday Slack?) accounts for new members '''
  logger.debug("Create new Accounts")
  createMissingMemberAccounts(added,isTest,False)

	# Canary test 

	if current_app.config['globalConfig'].Config.has_option('Payments','Canary'):
					canary = current_app.config['globalConfig'].Config.get('Payments','Canary')
					check = accesslib.quickSubscriptionCheck(member=canary)
					if check == "No Subscription":
						logger.critical("No subscription found for Adam.Shey")
						return

  db.session.commit()
  logger.debug("New Member/Sub data Committed")
  

def searchMembers(searchstr):
  sstr = "%" + searchstr + "%"
  q = Member.query
  q = q.filter(Member.firstname.ilike(sstr) | 
      (Member.lastname.ilike(sstr)) | 
      (Member.alt_email.ilike(sstr)) | 
      (Member.email.ilike(sstr)))
  return q.all()


''' Try to match subscriptions to existing member records - TODO - "new/update" flag '''
def matchMissingMembers(missing):
    newMembers = []
    ''' Return UNMACHED ones - i.e. new subs'''
    for s in missing:
        mm = Member.query.filter(Member.membership == s.membership).one_or_none()
				if mm:
								logger.debug("MEMBERSHIP MATCH - %s %s %s IS %s" % (s.name,s.email,s.subid,mm.member))
								s.member_id=mm.id
        else:
								q = Member.query
								q = q.filter(Member.alt_email.ilike(s.email))
								q = q.filter(Member.stripe_name.ilike(s.name)) # TODO BKG FIX - Depricate - use first and last names only
								try:
										mm = q.one_or_none()
										if mm:
												logger.debug("email/name MATCH - %s %s %s IS %s" % (s.name,s.email,s.subid,mm.member))
												s.member_id = mm.id
												mm.membership = s.membership
												# We APPEAR to have a match Just update the sub record w/ existing member ID
												# Remember - this gets committed at the VERY end when everything is DONE
										else:
												# No match - create new one
												logger.debug("NO MATCH - %s %s %s" % (s.name,s.email,s.subid))
												newMembers.append(s)
								except:
										mm=None
										logger.warning("MULTIPLE MATCHES - FIX MANUALLY  - %s %s %s" % (s.name,s.email,s.subid))


    return newMembers

def createMember(m):
    """Add a member entry to the database"""
    if 'memberid' not in m or m['memberid'] != '':
        m['memberid'] = m['firstname'] + "." + m['lastname']
    sqlstr = "Select member from members where member = '%s'" % m['memberid']
    members = dbutil.query_db(sqlstr)
    if members:
        return {'status': 'error','message':'That User ID already exists'}
    else:
        # TODO: Handle missing values?
        sqlstr = """insert into members (member,firstname,lastname,phone,plan,nickname,updated_date,access_enabled,active)
                    VALUES ('%s','%s','%s','%s','','%s',DATETIME('now'),'0','0')
                 """ % (m['memberid'],m['firstname'],m['lastname'],m['phone'],m['nickname'])
        dbutil.execute_db(sqlstr)
        dbutil.get_db().commit()
    return {'status':'success','message':'Member %s was created' % m['memberid']}

def getMissingMembers():
    """Return details from active Subscriptions for name+email combination not in Members table"""
    missing = Subscription.query.filter(Subscription.member_id == None)
    #missing = missing.filter(Subscription.active == 'true')
    missing = missing.filter(Subscription.plan != 'workspace')
    missing = missing.filter(Subscription.plan != 'trial')
    missing = missing.all()

    for s in missing:
            logger.debug("Missing Subscription: %s %s id %s" % (s.subid,s.name,s.email))

    return missing

    
def addMissingMembers(missing):
    newMembers=[]
    logger.info("Checking for any Subscriptions without a matching Membership entry")
    members = []
    bl_entries = Blacklist.query.all()
    ignorelist = []
                     
    for b in bl_entries:
        ignorelist.append(b.entry)
    for p in missing:
				logger.debug("Check add new for %s active %s expires %s" % (p.email,p.active,p.expires_date))
        if p.subid in ignorelist:
            logger.info("Explicitly ignoring subscription id %s" % p.subid)
            continue
        elif p.email in ignorelist:
            logger.info("Explicitly ignoring email %s" % p.email)
            continue
        elif p.customerid in ignorelist:
            logger.info("Explicitly ignoring customer id %s" % p.customerid)
            continue
        elif p.active.lower() != "true":
            logger.info("Skipping create for inactive sub %s id \"%s\"" % (p.customerid,p.active.lower()))
            continue
        elif p.expires_date < datetime.now():
            logger.info("Skipping create for expired sub %s" % p.customerid)
            continue
        else:
            logger.info("Missing member: %s (%s) (%s)" % (p.name,p.email,p.created_date))
            members.append({'name':p.name,'email':p.email,'plan':p.plan,'active':p.active,'created':p.created_date})

            # TODO - BKG BUG FIX this is where we need to know if this was an existing member or not - Refuse
            # to add if so - report to someone for correction
            i=0
            rootname = p.name.replace(' ','.')
            
            mname =None
            while not mname:
                if i==0:
                    mname = rootname
                else:
                    mname = rootname+str(i)
                if (Member.query.filter(Member.member==mname).count() == 1): mname=None
                i+=1
            mm = Member()
            mm.member = mname
            nameparts = utilities.nameToFirstLast(rootname)
            mm.firstname = nameparts['first']
            mm.lastname = nameparts['last']
            mm.alt_email = p.email
            mm.active = p.active
            mm.stripe_name = p.name # TODO BKG FIX - Depricate - use first and last names only
            mm.time_created = p.created_date
            mm.time_updated = p.created_date
            db.session.add(mm)
            db.session.flush()
            s = Subscription.query.filter(Subscription.email==p.email).filter(Subscription.name==p.name).one()
            logger.debug("Adding new member %s for subscription %s MemberID %s" % (mname, p.subid,mm.id))
            s.member_id=mm.id
            db.session.add(Logs(member_id=mm.id,event_type=eventtypes.RATTBE_LOGEVENT_CONFIG_NEW_MEMBER_PAYSYS.id))
            newMembers.append(mm)
    # NOTE we are not committing until all slack and google accounts have been created!!
    return newMembers

def googleEmailExists(m):
  # Member ID is available, check if existing account. If so, manual data check is required for now.
  search = google.searchEmail(m.member)
  logger.debug("Google email search for %s returns %s" % str(m.member,search))
  return (len(search > 0))
  
  
def createMissingMemberAccounts(members,isTest=True,searchGoogle=False):
    """For any Member without a Member ID, create one (includes Google Domain account). If we can't, notify admins"""
    
    for m in members:
        # Handle duplicate names through numeric additions
        if searchGoogle and googleEmailExists(m):
          msg = "Manual intervention required: %s (%s) needs an account created. Memberid %s is not used, but has an account." % (m['stripe_name'],m['alt_email'],memberid)
          logger.error(msg)
          continue
          
            
        # Create the account
        if isTest:
            logger.warn("Need to see if we really need an account for %s (%s) or if this is a data issue" % (m.member,m.alt_email))
        else:
            nameparts = utilities.nameToFirstLast(m.member)
            # - Use first portion of name as Firstname, all remaining as Familyname
            password = "%s%d%d" % (nameparts['last'],random.randint(1,100000),len(nameparts['last']))
            google.createUser(nameparts['first'],nameparts['last'],m.member,m.alt_email,password)
            google.sendWelcomeEmail(m.member,password,m.alt_email)
        

        
def _syncMemberPlans():
    """Update Members table with currently paid-for plan from Subscriptions"""
    # Will this work when someone is on multiple subscriptions?
    sqlstr = """update members set plan = (select plan from subscriptions where members.name=subscriptions.name and members.email=subscriptions.email)
            where name in (select name from subscriptions)"""
    execute_db(sqlstr)
    get_db().commit()
    

def addMissingMembers_new(subs):
    """Add to Members table any members in Subscriptions but not in Members"""
    # Find all (Name + Email) keys where we don't have a member
    sqlstr = """select s.name, s.email, s.customerid select p.member from subscriptions p
            left outer join members m on p.member=m.member where m.member is null"""
    members = query_db(sqlstr)
    sqlstr2 = "select entry,entrytype from blacklist"
    bl_entries = query_db(sqlstr2)
    missingids = []
    users = []
    for m in members:
        missingids.append(m['member'])
    ignorelist = []
    for b in bl_entries:
        ignorelist.append(b['entry'])
    sqlstr3 = "select "
    for s in subs:
        if s['userid'] in missingids:
            if s['customerid'] in ignorelist:
                print("Customer ID is in the ignore list")
                continue
            users.append((s['userid'],s['firstname'],s['lastname'],s['membertype'],s['phone'],s['email'],"Datetime('now')"))
    if len(users) > 0:
        cur = get_db().cursor()
        cur.executemany('INSERT into members (member,firstname,lastname,plan,phone,alt_email,updated_date) VALUES (?,?,?,?,?,?,?)', users)
        get_db().commit()
    return len(users)    


# ------------------------------------------------------------
# Google Accounts and Welcome Letters
# This appears to be UNUSED???
# -----------------------------------------------------------

def _createNewGoogleAccounts():
    """Check for any user created in the last 3 days who does not have a Makeitlabs.com account"""
    sqlstr = "select m.member,m.firstname,m.lastname,p.email from members m inner join payments p on m.member=p.member where p.created_date >= Datetime('now','-3 day') and p.expires_date >= Datetime('now')"
    newusers = query_db(sqlstr)
    for n in newusers:
        # Using emailstr search to get around wierd hierarchical name mismatch
        emailstr = "%s.%s@makeitlabs.com" % (n['firstname'],n['lastname'])
        users = google_admin.searchEmail(emailstr)
        if users == []:
            # TODO: Change this to logging
            print "Member %s may need an account (%s.%s)" % (n['member'],n['firstname'],n['lastname'])
            ts = time.time()
            password = "%s-%d" % (n['lastname'],ts - (len(n['email']) * 314))
            print "Create with password %s and email to %s" % (password,n['email'])
            user = google_admin.createUser(n['firstname'],n['lastname'],n['email'],password)
            google_admin.sendWelcomeEmail(user,password,n['email'])
            print("Welcome email sent")
        else:
            print "Member appears to have an account: %s" % users


# Run with: python ./authserver.py --command syncmemberpayments
def cli_syncmemberpayments(cmd,**kwargs):
    if 'app' in kwargs: app=kwargs['app']
    args=cmd[1:]

    if '--help' in args:
        print """
Options:
    --force  Force creation of Google and Slack accounts - even in a non-production server  
    --test   DO NOT create Google and Slack accounts - even in a non-production server  
        """
        return

    isTest=False
    if '--test' in args:
        isTest=True
    if current_app.config['globalConfig'].DeployType.lower() != "production":
      if '--force' in args:
        logger.info( "Non-production environments - but you are FORCING account creation")
      else:
        logger.info( "Non-production environments - no accounts will be created")
        isTest=True

    syncWithSubscriptions(isTest)  
