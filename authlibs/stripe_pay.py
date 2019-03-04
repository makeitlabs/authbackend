#!/usr/bin/env python
"""
This module handles Processing Stripe payments APIs

The parent module should expect to call the following two methods:

1) testSystem() - Ensure the system is reachable and passes basic tests
2) getSubscribers() - Return a payment-system Independent JSON structure consisting of account data

"""

import config
import stripe
import sys
from datetime import datetime,date
import time
import re
import utilities

import logging
logger = logging.getLogger(__name__)

# TODO: Sync stripe customers
def getCustomers(sinceDate=None):
    '''Get a list of Customers, each entry is a dict of customer data '''
    if sinceDate == None:
        sinceDate = datetime(2010,1,1)
    timestamp = int(time.mktime(sinceDate.timetuple()))
    #print(timestamp)
    logger.info("Getting customers created since given date")
    stripe.api_key = Config.get('Stripe','token')
    has_more = True
    customers = []
    while has_more:
        output = stripe.Customer.all(created={"gte":timestamp})
        for c in output['data']:
            cdate = datetime.fromtimestamp(c['created'])
            newc = {'customerid': c['id'], 'email': c['email'], 'created_date':''}
            customers.append(newc)
        has_more = output['has_more']
    return customers

def getSubscriptions(status=None):
    '''Get all Subscriptions'''
    if status is None:
        status = "all"
    subscriptions = []
    logger.info("Getting Stripe subscriptions with status '%s'" % status)
    subs = stripe.Subscription.list(status=status,limit=50)
    for s in subs.auto_paging_iter():
        subscriptions.append(s)
        #print(s)
    return subscriptions

def reportError(s):
    print("ERROR: %s" % s)

def getSubscriptionsJSON():
    '''Get a payment system independent JSON structure with subscription data'''
    # Resulting structure keys
    #  customerid,subid,firstname,lastname,userid,email,membertype,plan,active,created,updatedon,expires,phone
    # For Stripe, customerid and subid are different.
    subs = getSubscriptions()
    #import pickle
    #pickle.dump(subs,open("slack_prod_data.pickle","w"))
    #subs = pickle.load(open("slack_prod_data.pickle"))
    #print(subs)
    subscribers = list()
    noemail = list()
    notactive = list()
    # Iterate through all subscriptions
    for s in subs:
        names = []
        emails = []
        subid = s['id']
        customerid = s['customer']
        phone = ''
        need_emails = True
        if 'plan' not in s:
            print "ERROR - no plan in ",s['customer']
            continue
        if s['plan'] is None:
            print "NULL plan for  ",s['customer']
            continue
        if 'id' not in s['plan']:
            print "ERROR - no id in plan for ",s['customer']
            continue
        plan = s['plan']['id']

        # NEW: Check for archived metadata flag to help with old records we still want to retain
        if 'archived' in s['metadata']:
            print("Archived subscription (%s, %s), ignoring")
        # Customize: This section is specific to our Plan names in Stripe
        if plan in ['hobbyist']:
            plantype = "hobbyist"
        elif plan in ['free','pro','produo','board','resourcemgr']:
            plantype = 'pro'
        elif "group_pro" in plan:
            plantype = 'pro'
        elif "group" in plan:
            plantype = 'hobbyist'
        elif "WORKSPACE" in plan:
            # TODO: More alerting...
            print("Workspace check: %s  Status: %s (%s)" % (s['plan']['id'], s['status'], subid))
            #continue BKG wants to remove
        else:
            plantype = "unknown"
            need_emails = False
        if s['status'] in ['active','trialing']:
            active = 'true'
        else:
            active = 'false (%s)' % s['status']
            # Remove "Cancelled" from list? this seems to show duplicate records for old subs.
            if s['status'] == "cancelled":
                print("Cancelled entry, may simply be old subscription: %s : %s : %s" % (s['plan']['id'], subid, s['metadata']))
                continue


        # expires_on = datetime.fromtimestamp(c['current_period_end']).strftime('%Y-%m-%d')
        expires = utilities._utcTimestampToDatetime(s['current_period_end'])
        created = utilities._utcTimestampToDatetime(s['created'])
        updated = utilities.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        # Extract Name and Email Metadata from record
        # - Expecting comma-delimited!
        if need_emails:
          if s['metadata'] == {}:
            reportError("STRIPE PAYMENTS: SUBSCRIPTION %s: No metadata" % subid)
            continue
          if 'names' in s['metadata']:
            names = s['metadata']['names'].split(",")
          if 'emails' in s['metadata']:
            emails = s['metadata']['emails'].split(",")
          if len(names) != len(emails) or len(names) == 0:
            reportError("STRIPE PAYMENTS: SUBSCRIPTION %s: Problem in Names or Emails metadata (%s)" % (subid,s['metadata']))
            continue

        for (m,e) in zip(names,emails):
            # For each person, create an associated subscription record
            name = utilities._safestr(m)
            email = utilities._safeemail(e)
            # Membership must be unique to each member - totally definable by pay system
            membership = "stripe:"+name.replace(" ",".")+":"+email
            sub = {'customerid': customerid, 'subid': subid, 'name': name, 'planname': plan, 'plantype': plantype, 'email': email, 'active': active, 'created': created, 'updatedon': updated, 'expires': expires, 'phone': phone , 'membership':membership}
            subscribers.append(sub)
            #print(sub)
            print "IMPORTING",membership,email,name,expires,active
    return subscribers


def getSubscriptionsJSON2():
    '''Get a payment system independent JSON structure with subscription data'''
    # Resulting structure keys
    #  customerid,subid,firstname,lastname,userid,email,membertype,plan,active,created,updatedon,expires,phone
    subs = getSubscriptions()
    print(subs)
    subscribers = list()
    noemail = list()
    notactive = list()
    # Iterate through all subscriptions
    for s in subs:
        names = []
        emails = []
        subid = s['id']
        customerid = s['customer']
        phone = ''
        need_emails = True
        plan = s['plan']['id']
        # Customize: This section is specific to our Plan names in Stripe
        if plan in ['hobbyist']:
            plantype = "hobbyist"
        elif plan in ['free','pro','produo','board','resourcemgr']:
            plantype = 'pro'
        elif "group" in plan:
            plantype = 'pro'
        elif "workspace" in plan:
            plantype = 'workspace'
            need_emails = False
        else:
            plantype = "unknown"
            need_emails = False
        if s['status'] in ['active','trialing']:
            active = 'true'
        else:
            active = 'false (%s)' % s['status']
            need_emails = False

        # Extract Name and Email Metadata from record
        # - Expecting comma-delimited!
        if need_emails:
          if 'names' in s['metadata']:
            names = s['metadata']['names'].split(",")
          if 'emails' in s['metadata']:
            emails = s['metadata']['emails'].split(",")
          if len(names) != len(emails) or len(names) == 0:
            reportError("STRIPE PAYMENTS: SUBSCRIPTION %s: Problem in Names or Emails metadata (%s)" % (subid,s['metadata']))
            continue

        # expires_on = datetime.fromtimestamp(c['current_period_end']).strftime('%Y-%m-%d')
        expires = utilities._utcTimestampToDatetime(s['current_period_end'])
        created = utilities._utcTimestampToDatetime(s['created'])
        updated = utilities.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        for (m,e) in zip(names,emails):
            # For each person, create an associated subscription record
            name = utilities._safestr(m)
            email = utilities._safeemail(e)
            sub = {'customerid': customerid, 'subid': subid, 'name': name, 'planname': plan, 'plantype': plantype, 'email': email, 'active': active, 'created': created, 'updatedon': updated, 'expires': expires, 'phone': phone }
            subscribers.append(sub)
            print(sub)
    return subscribers


def selftest():
    setupStripe()
    logger.info("Running Stripe selftest")
    print(getSubscriptionsJSON())
    return True

def setupStripe():
    logger.info("Setting up Stripe")
    stripe.api_key = config.stripe['token']

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    selftest()
