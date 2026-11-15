#!/usr/bin/env python
#vim:tabstop=2:expandtab
# Membership-related functions, to decouple from UI

from . import config
from . import dbutil
from . import utilities
import random
import threading
from collections import defaultdict
from . import config
import sys
import argparse
from .db_models import db, Subscription, Member, Blacklist, Logs
from sqlalchemy.exc import OperationalError
from authlibs.memberFolders.memberFolders import createMemberFolder
import configparser
from . import eventtypes
from datetime import datetime
import time
from flask import current_app

from .templateCommon import *

from . import google_admin as google
from . import accesslib

def syncWithSubscriptions(isTest=False):
  '''Use the latest Subscription data to ensure Membership list is up to date'''
  try:
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
    createMissingMemberAccounts(added,isTest,True)

    ''' Sync group field for existing linked members if group is empty/null '''
    linked_subs = Subscription.query.filter(Subscription.member_id != None).filter(Subscription.group != None).all()
    for ls in linked_subs:
      if ls.group and ls.group.strip() != "":
        m_rec = Member.query.filter(Member.id == ls.member_id).one_or_none()
        if m_rec and (not m_rec.group or m_rec.group.strip() == ""):
          m_rec.group = ls.group.strip()

    # Canary test 

    if current_app.config['globalConfig'].Config.has_option('Payments','Canary'):
      canary = current_app.config['globalConfig'].Config.get('Payments','Canary')
      check = accesslib.quickSubscriptionCheck(member=canary)
      if check == "No Subscription":
          logger.critical("No subscription found for Adam.Shey")
          db.session.rollback()
          return 1

    # Check subscription state transitions for existing members
    from . import payments
    pre_active = payments.get_pre_sync_active_members()
    if pre_active is not None:
      now = datetime.utcnow()
      linked_subs = Subscription.query.filter(Subscription.member_id != None).all()
      post_active = set(s.member_id for s in linked_subs if payments.is_sub_active(s, now))
      added_ids = set(m.id for m in added if hasattr(m, 'id') and m.id)

      # 1. Activated: Was inactive before, now active, and NOT a brand new member added in this run
      reactivated_ids = (post_active - pre_active) - added_ids
      for mid in reactivated_ids:
        logger.info("Subscription Activated by Payment System for member_id %s" % mid)
        db.session.add(Logs(member_id=mid, event_type=eventtypes.RATTBE_LOGEVENT_CONFIG_SUB_ACTIVATED_PAYSYS.id,
                            message="Subscription activated via payment system"))

      # 2. Canceled/Expired: Was active before, now not active
      canceled_ids = pre_active - post_active
      for mid in canceled_ids:
        logger.info("Subscription Canceled by Payment System for member_id %s" % mid)
        db.session.add(Logs(member_id=mid, event_type=eventtypes.RATTBE_LOGEVENT_CONFIG_SUB_CANCELED_PAYSYS.id,
                            message="Subscription canceled/expired via payment system"))

    db.session.commit()
    payments.clear_pre_sync_active_members()
    logger.debug("New Member/Sub data Committed")
    return 0
  except OperationalError as e:
    logger.error("syncWithSubscriptions: database locked/failed: %s" % str(e))
    db.session.rollback()
    return 2

def syncWithSubscriptions_with_retry(isTest=False, retries=5, delay=2):
  """Call syncWithSubscriptions, retrying if DB is locked (return code 2)."""
  for attempt in range(retries):
    res = syncWithSubscriptions(isTest)
    if res != 2:
      return res
    logger.warning("syncWithSubscriptions hit DB lock (attempt %d/%d). Retrying in %ds..." % (attempt + 1, retries, delay))
    time.sleep(delay)
  return 2
  

def searchMembers(searchstr):
  sstr = "%" + searchstr + "%"
  q = Member.query
  q = q.filter(Member.firstname.ilike(sstr) | 
      (Member.lastname.ilike(sstr)) | 
      (Member.alt_email.ilike(sstr)) | 
      (Member.email.ilike(sstr)) |
      (Member.group.ilike(sstr)))
  return q.all()


''' Try to match subscriptions to existing member records - TODO - "new/update" flag '''
def matchMissingMembers(missing):
    newMembers = []
    ''' Return UNMACHED ones - i.e. new subs'''
    for s in missing:
        mm = Member.query.filter(Member.membership == s.membership).one_or_none()
        if mm:
                logger.debug("MEMBERSHIP MATCH - %s %s %s IS %s" % (s.name,s.email,s.subid,mm.member))
                if getattr(s, 'group', None) and s.group and (not mm.group or mm.group.strip() == ""):
                  mm.group = s.group.strip()
                # If we had already done a email/name match (below) - invalidate it so we dont get dupes
                ss= Subscription.query.filter(Subscription.member_id == mm.id).one_or_none()
                if (ss):
                  logger.debug("-Invalidated prior sub match to - %s %s %s FOR %s" % (ss.name,ss.email,ss.subid,mm.member))
                  ss.member_id=None
                s.member_id=mm.id
        else:
                q = Member.query
                q = q.filter(Member.alt_email.ilike(s.email))
                q = q.filter(Member.stripe_name.ilike(s.name)) # TODO BKG FIX - Depricate - use first and last names only
                try:
                    mm = q.one_or_none()
                    if mm:
                        logger.debug("email/name MATCH - %s %s %s IS %s" % (s.name,s.email,s.subid,mm.member))
                        if getattr(s, 'group', None) and s.group and (not mm.group or mm.group.strip() == ""):
                          mm.group = s.group.strip()
                        # Avoid DUPLICATE match if MEMBERSHIP MATCH already done (above)
                        ss = Subscription.query.filter(Subscription.member_id == mm.id).one_or_none()
                        if ss and ss.active=="true":
                          logger.debug("-Avoided overwrite ACTIVE sub match - %s %s %s FOR %s" % (ss.name,ss.email,ss.subid,mm.member))
                        elif ss:
                          logger.debug("-Avoided overwrite INACTIVE prior sub match - %s %s %s FOR %s" % (ss.name,ss.email,ss.subid,mm.member))
                          s.member_id = mm.id
                          mm.membership = s.membership
                        else:
                          logger.debug("-Avoided overwrite NOSUB prior sub match")
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

    #for s in missing:
    #        logger.debug("Missing Subscription: %s %s id %s" % (s.subid,s.name,s.email))

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
            logger.debug("Explicitly ignoring subscription id %s" % p.subid)
            continue
        elif p.email in ignorelist:
            logger.debug("Explicitly ignoring email %s" % p.email)
            continue
        elif p.customerid in ignorelist:
            logger.debug("Explicitly ignoring customer id %s" % p.customerid)
            continue
        elif p.active.lower() != "true":
            logger.debug("Skipping create for inactive sub %s id \"%s\"" % (p.customerid,p.active.lower()))
            continue
        elif p.expires_date < datetime.now():
            logger.debug("Skipping create for expired sub %s" % p.customerid)
            continue
        else:
            logger.debug("Missing member: %s (%s) (%s)" % (p.name,p.email,p.created_date))
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
            mm.plan = p.plan
            mm.stripe_name = p.name # TODO BKG FIX - Depricate - use first and last names only
            mm.time_created = p.created_date
            mm.time_updated = p.created_date
            mm.email_confirmed_at = datetime.now()
            if getattr(p, 'group', None) and p.group:
                mm.group = p.group.strip()
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
  logger.debug("Google email search for %s returns %s" % (m.member,search))
  return (len(search) > 0)
  
  
def _forwarding_worker(makeitlabs_email, forward_to_email, initial_delay=30, max_retries=3, retry_delay=30):
    """Background worker: waits for Gmail to be provisioned, then sets up forwarding.
    Runs in a daemon thread so it won't block the web request or prevent shutdown."""
    import time
    time.sleep(initial_delay)
    for attempt in range(1, max_retries + 1):
        try:
            google.setupEmailForwarding(makeitlabs_email, forward_to_email)
            logger.info("Background forwarding setup succeeded for %s -> %s (attempt %d)" %
                        (makeitlabs_email, forward_to_email, attempt))
            return
        except BaseException as e:
            if "Invalid forwarding address" in str(e) and "400" in str(e):
                logger.info("Background forwarding 'Invalid forwarding address' error ignored for %s -> %s (treated as success)" %
                            (makeitlabs_email, forward_to_email))
                return
            logger.warning("Background forwarding attempt %d/%d failed for %s -> %s: %s" %
                           (attempt, max_retries, makeitlabs_email, forward_to_email, str(e)))
            if attempt < max_retries:
                time.sleep(retry_delay)
    logger.error("All %d background forwarding attempts failed for %s -> %s" %
                 (max_retries, makeitlabs_email, forward_to_email))

def _start_forwarding_background(makeitlabs_email, forward_to_email):
    """Kick off email forwarding setup in a background thread.
    Returns immediately so the caller (web request) is not blocked."""
    t = threading.Thread(
        target=_forwarding_worker,
        args=(makeitlabs_email, forward_to_email),
        daemon=True
    )
    t.start()
    logger.info("Started background forwarding thread for %s -> %s" %
                (makeitlabs_email, forward_to_email))

def createMissingMemberAccounts(members,isTest=True,searchGoogle=False):
    """For any Member without a Member ID, create one (includes Google Domain account). If we can't, notify admins"""
    
    for m in members:
        # Handle duplicate names through numeric additions
        logger.warn("Check Google member account for %s (%s)" % (m.member,m.alt_email))
        if searchGoogle and not isTest and googleEmailExists(m):
          msg = "Manual intervention required: %s (%s) needs an account created. Memberid %s is not used, but has an account." % (m.stripe_name, m.alt_email, m.id)
          logger.error(msg)
          continue
          
            
        # Create the account
        if isTest:
            logger.warn("Need to see if we really need an account for %s (%s) or if this is a data issue" % (m.member,m.alt_email))
        else:
            nameparts = utilities.nameToFirstLast(m.member)
            # - Use first portion of name as Firstname, all remaining as Familyname
            password = "%s%d%d" % (nameparts['last'],random.randint(100000,999999),len(nameparts['last']))
            try:
              google.createUser(nameparts['first'],nameparts['last'],m.member,m.alt_email,password)
              m.email=m.member.lower()+"@makeitlabs.com"
              google.sendWelcomeEmail(m.member,password,m.alt_email)
              msg = "Created new Google account for %s %s" % (m.member,m.alt_email)
              logger.warn(msg)
              # Set up email forwarding in background thread (Gmail may not be
              # ready immediately after account creation, so we delay and retry)
              _start_forwarding_background(m.email, m.alt_email)
            except BaseException as e:
              msg = "Failed createing Google account for %s: %s" % (m.alt_email,str(e))
              logger.error(msg)
            createMemberFolder(m)
        

        
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
            print ("Member %s may need an account (%s.%s)" % (n['member'],n['firstname'],n['lastname']))
            ts = time.time()
            password = "%s-%d" % (n['lastname'],ts - (len(n['email']) * 314))
            print ("Create with password %s and email to %s" % (password,n['email']))
            user = google_admin.createUser(n['firstname'],n['lastname'],n['email'],password)
            google_admin.sendWelcomeEmail(user,password,n['email'])
            print("Welcome email sent")
        else:
            print ("Member appears to have an account: %s" % users)


# Run with: python ./authserver.py --command syncmemberpayments
def cli_syncmemberpayments(cmd,**kwargs):
    if 'app' in kwargs: app=kwargs['app']
    args=cmd[1:]

    if '--help' in args:
        print ("""
Options:
    --force  Force creation of Google and Slack accounts - even in a non-production server  
    --test   DO NOT create Google and Slack accounts - even in a non-production server  
        """)
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

    res = syncWithSubscriptions_with_retry(isTest)
    if res != 0:
      logger.error("cli_syncmemberpayments completed with status code %d" % res)

def cli_createmembertest(cmd,**kwargs):
    google.createUser("Testy","McTesterson","testy.testerson","test@example.com","test123abcd!")

def cli_testgooglecreate(cmd,**kwargs):
    """Test the full Google account creation + email forwarding pipeline.
    Creates a real Google account (unless --test), sends welcome email,
    and sets up email forwarding. Does NOT touch the database."""
    args = cmd[1:]

    if '--help' in args:
        print("""
Usage: testgooglecreate [firstname] [lastname] [alt_email] [--test]

  Creates a Google account (firstname.lastname@makeitlabs.com), sends a
  welcome email to alt_email, and sets up email forwarding from the new
  makeitlabs.com address to alt_email.

  Does NOT create any database records.

  Options:
    --test   Dry run: print what would happen but don't call Google APIs
    --help   Show this help

  Defaults to Testy McTesterson <test@example.com> if no args given.
        """)
        return

    isTest = '--test' in args
    args = [a for a in args if not a.startswith('--')]

    firstname = args[0] if len(args) > 0 else "Testy"
    lastname  = args[1] if len(args) > 1 else "McTesterson"
    alt_email = args[2] if len(args) > 2 else "test@example.com"
    userid = (firstname + "." + lastname).replace(" ", ".")
    makeitlabs_email = userid.lower() + "@makeitlabs.com"
    password = "%s%d%d" % (lastname, random.randint(100000, 999999), len(lastname))

    print("=== Google Account Creation Test ===")
    print("  First name:    %s" % firstname)
    print("  Last name:     %s" % lastname)
    print("  User ID:       %s" % userid)
    print("  MakeIt email:  %s" % makeitlabs_email)
    print("  Alt email:     %s" % alt_email)
    print("  Password:      %s" % password)
    print("  Mode:          %s" % ("DRY RUN" if isTest else "LIVE"))
    print()

    if isTest:
        print("[TEST] Would create Google user: %s" % userid)
        print("[TEST] Would send welcome email to: %s" % alt_email)
        print("[TEST] Would set up forwarding: %s -> %s" % (makeitlabs_email, alt_email))
        print("\nDry run complete. No API calls made.")
        return

    # Step 1: Create Google account
    print("Step 1: Creating Google account...")
    try:
        google.createUser(firstname, lastname, userid, alt_email, password)
        print("  OK - Google account created for %s" % userid)
    except BaseException as e:
        print("  FAILED - %s" % str(e))
        print("\nAborting (no account to forward from).")
        return

    # Step 2: Send welcome email
    print("Step 2: Sending welcome email to %s..." % alt_email)
    try:
        google.sendWelcomeEmail(userid, password, alt_email)
        print("  OK - Welcome email sent")
    except BaseException as e:
        print("  FAILED - %s" % str(e))
        print("  (Continuing to forwarding setup...)")

    # Step 3: Set up email forwarding (retry — Gmail may not be provisioned yet)
    max_retries = 20
    retry_delay = 10
    print("Step 3: Setting up email forwarding %s -> %s..." % (makeitlabs_email, alt_email))
    print("  (Will retry up to %d times, %d seconds apart)" % (max_retries, retry_delay))
    for attempt in range(1, max_retries + 1):
        try:
            google.setupEmailForwarding(makeitlabs_email, alt_email)
            print("  OK - Email forwarding enabled (attempt %d)" % attempt)
            break
        except BaseException as e:
            if "Invalid forwarding address" in str(e) and "400" in str(e):
                print("  OK - Ignoring 'Invalid forwarding address' error (treated as success)")
                break
            print("  Attempt %d/%d failed: %s" % (attempt, max_retries, str(e)))
            if attempt < max_retries:
                print("  Waiting %d seconds..." % retry_delay)
                time.sleep(retry_delay)
            else:
                print("  FAILED - All %d attempts exhausted" % max_retries)

    print("\nDone.")

def cli_creatememberfoldertest(cmd,**kwargs):
    bkg = Member.query.filter(Member.member=="Bradley.Goodman").one()
    createMemberFolder(bkg)
