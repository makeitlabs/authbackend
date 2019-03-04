#!/usr/bin/env python
#vim:tabstop=2:expandtab

#import config
#import sqlite3, time
#from db_models import db, Subscription
#from datetime import datetime
#import utilities as authutils

from templateCommon import *

from datetime import datetime

'''
Database = "makeit.db"
DBCON = None

import logging
logger = logging.getLogger(__name__)

def connect_db():
    """Convenience method to connect to the globally-defined database"""
    con = sqlite3.connect(Database,check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def get_db():
    """Convenience method to get the current DB loaded by Flask, or connect to it if first access"""
    global DBCON
    if DBCON is None:
        DBCON = connect_db()
    return DBCON

def query_db(query, args=(), one=False):
    """Convenience method to execute a basic SQL query against the current DB. Returns a dict unless optional args used"""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query,autoCommit=True):
    """Convenience method to execute a non-query SQL statement against the current DB."""
    cur = get_db().cursor()
    cur.execute(query)
    if autoCommit:
        get_db().commit()
    cur.close()
'''

    
# ----------------------
# Payment/Subscription-related DB Routines
# -----------------------

def _clearPaymentData(paytype):
    """Remove all payment data for the configured paysystem type from the payments table"""
		"""
    logger.info("Clearing subscription data")
    sql = "delete from payments where paysystem= '%s'" % paytype
    execute_db(sql)
    get_db().commit()
		"""

		
    
"""
def _addPaymentData(subs,paytype):
    #From a JSON list of subscribers, add entries to the Payments table
    users = []
    # Blacklist is for specific records we don;t want to process
    # - For example Pinpayments records that cannot be purged
    blacklist = query_db("select entry from blacklist")
    bad = []
    for b in blacklist:
        bad.append(b['entry'])
    logger.info("BLACKLIST: %s" % bad)
    for sub in subs:
        if sub['customerid'] in bad:
            logger.info("BLACKLIST: IGNORING CUSTOMERID %s for %s" % (sub['customerid'],sub['userid']))
        else:
            users.append((sub['userid'],sub['email'],paytype,sub['membertype'],sub['customerid'],sub['created'],sub['expires'],sub['updatedon'],time.strftime("%c")))
    cur = get_db().cursor()
    cur.executemany('INSERT into payments (member,email,paysystem,plan,customerid,created_date,expires_date,updated_date,checked_date) VALUES (?,?,?,?,?,?,?,?,?)', users)
    get_db().commit()
"""
    
       
def _clearSubscriptionData(paytype):
    """Remove all payment data for the configured paysystem type from the payments table"""
		"""
    sql = "delete from subscriptions where paysystem= '%s'" % paytype
    execute_db(sql)
    get_db().commit()
		"""
		Subscription.query.filter(Subscription.paysystem == paytype).delete()
    
    
def updateSubscriptions(module):
    subs = pay.getSubscriptions(module)
    fsubs = pay.filterSubscriptions(subs)
    _clearSubscriptionData(module)
    # Do we want just valid info? if so pass fsubs['valid']
    _addSubscriptionData(subs,module)
    
def _addSubscriptionData(subs,paytype):
    '''From a JSON list of subscribers, add entries to Subscriptions table'''
    users = []
    # Blacklist is for specific records we don't want to process
    # - For example Pinpayments records that cannot be purged
    #con = connect_db()
    #blacklist = con.execute("select entry from blacklist")
		blacklist = Blacklist.query.all()
    bad = []
    for b in blacklist:
        bad.append(b.entry)
    logger.info("BLACKLIST: %s" % bad)
    for sub in subs:
        #print  "FOUND",sub['name'],sub['email'],sub['active'], "Exp:",authutils.parse_datetime(sub['expires']), "Cre:",authutils.parse_datetime(sub['created'])
        if sub['customerid'] in bad:
            logger.info("BLACKLIST: IGNORING CUSTOMERID %s for %s" % (sub['customerid'],sub['name']))
        else:
            #print "PLANS",sub['planname'],sub['plantype']
            s = Subscription.query.filter(Subscription.membership==sub['membership']).one_or_none()
            if not s: 
                s=Subscription(membership=sub['membership'])
                db.session.add(s)
            else:
                # We found another one. Which one do we use??

                if s.active.lower() != "true"  and sub['active'].lower() == "true":
                    pass
                    print "REPLACING w/ INACTIVE record for ",sub['name'],sub['email'],"Created",sub['created'],"Expires",sub['expires']
                if s.active.lower() == "true"  and sub['active'].lower() != "true":
                    # skip if old was active, but new is inactive
                    print "SKIPPING INACTIVE record for ",sub['name'],sub['email'],"Created",sub['created'],"Expires",sub['expires']
                    continue 
                elif s.expires_date < authutil.parse_datetime(sub['expires']):
                    print "REPLACING NEWER EXPIRE records ",sub['name'],sub['email'],"Created",sub['created'],"Expires",sub['expires'],sub['active'],"VS Created",s.created_date,"expires",s.expires_date,s.active
                elif s.created_date > authutil.parse_datetime(sub['created']):
                    #print "Old",s.created_date
                    #print "New",authutil.parse_datetime(sub['created'])
                    print "SKIPPING older records ",sub['name'],sub['email'],"Created",sub['created'],"Expires",sub['expires'],sub['active'],"VS Created",s.created_date,"expires",s.expires_date,s.active
                    continue 

                elif s.active.lower() == "true"  and sub['active'].lower() == "true":
                    print "WARNING - Two active records for  record for ",sub['name'],sub['email'],"Created",sub['created'],"Expires",sub['expires']

                print "OVERWRITE record for ",sub['name'],sub['email'],sub['created']
            s.paysystem = paytype
            s.subid = sub['subid']
            s.customerid = sub['customerid']
            s.name = sub['name']
            s.email = sub['email']
            s.plan = sub['plantype']
            s.expires_date = authutil.parse_datetime(sub['expires'])
            s.created_date = authutil.parse_datetime(sub['created'])
            s.updated_date = authutil.parse_datetime(sub['updatedon'])
            s.membership = sub['membership']
            s.checked_date = datetime.now()
            s.active = sub['active']
            users.append((sub['name'],sub['active'],sub['email'],paytype,sub['plantype'],sub['customerid'],sub['subid'],sub['created'],sub['expires'],sub['updatedon'],time.strftime("%c")))
            print "ADDING record for",sub['email'],sub['name']
    #db.session.commit() 




