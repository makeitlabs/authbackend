#!/usr/bin/env python
"""
Payment abstraction layer

This module is intended to load appropriate payment system-specific libs
and use them to complete Payment-related operations.

"""

import pinpayments as pinpay
import stripe_pay
import datetime
import utilities
import dbutil
import init
from sqlalchemy import func
from authlibs.db_models import db, Member, Resource, AccessByMember, Tool, Logs, UsageLog, Subscription

import config
import sys

import logging
logger = logging.getLogger(__name__)

setupDone = False


def getLastUpdatedDate():
	return db.session.query(func.max(Subscription.updated_date)).scalar()

def testPaymentSystems(modules=None):
    if modules is None:
        modules = config.payments['modules'].split(",")
    status = {}
    for m in modules:
        if m == 'pinpayments':
            logger.info("Testing Pinpayments..")
            status['pinpayments'] = pinpay.selftest()
        elif m == 'stripe':
            logger.info("Testing Stripe")
            status['stripe'] = stripe_pay.selftest()
        else:
            raise RuntimeError('Invalid payment system defined')
            return False
    for k in status:
      if status[k] == False:
        return False
    return True

def getSubscriptions(module=None):
    """Call the appropriate payment system module to get subscribers in JSON format"""
    if module == "pinpayments":
        return pinpay.getSubscriptionsJSON()
    elif module == "stripe":
        return stripe_pay.getSubscriptionsJSON()
    else:
        raise RuntimeError('Invalid payment system (%s) defined in INI file' % module)

def filterSubscriptions(subscriptions):
    """Filter JSON list of subscriptions into categories (valid,err_(email|plan|expired)) based on rules"""
    noemail = list()
    notactive = list()
    noplan = list()
    nouserid = list()
    validsubs = list()
    print("Filtering subscriptions - remember to check pinpay 'userid' to 'name' change")
    for sub in subscriptions:
        valid = True
        if not sub['email']:
            noemail.append(sub)
            logger.debug("No email for: %s" % sub)
            valid = False
        if valid and not sub['plantype']:
            logger.debug("No plan for: %s" % sub)
            noplan.append(sub)
            valid = False
        if valid and not sub['name']:
            logger("No name for: %s" % sub)
            nouserid.append(sub)
            valid = False
        if valid:
            validsubs.append(sub)
            if not _isFutureDate(sub['expires']):
                notactive.append(sub)
    return {'valid': validsubs, 'err_email': noemail, 'err_plan': noplan, 'err_expired': notactive, 'err_userid': nouserid}

def filterSubscriptions2(subscriptions):
    """Filter JSON list of subscriptions into categories (valid,err_(email|plan|expired)) based on rules"""
    noemail = list()
    notactive = list()
    noplan = list()
    nouserid = list()
    validsubs = list()
    for sub in subscriptions:
        if not sub['metadata']:
            print("MISSING META!")
        # Active or Trial Period
        if sub('status') in ['active','trialing']:
            validsubs.append(sub)
        elif sub('status') in ['past_due','unpaid']:
            print("Customer is Past due or Unpaid: %s (%s)" % (sub['metadata']['names'],sub['id']))
        else:
            print("Customer is cancelled or otherwise invalid: %s  (%s, %s)" % (sub['id'],sub['metadata']['names'],sub['id']))

def writeSubscribersTextfile(subs,filename):
    f = open(filename,'w')
    for sub in subs:
        print>>f, sub
    f.close()

def old_updatePaymentsData():
   subs = getSubscriptions(paysystem)
   fsubs = filterSubscriptions(subs)
   clearPaymentData('pinpayments')
   _addPaymentData(fsubs['valid'],'pinpayments')

# TODO: Update this for Stripe options
def chargeFee(module,memberid,name,group,description,amount):
    """Immediately apply a fee to the user's account"""
    if module == "pinpayments":
        force = True
        return pinpay.chargeFee(memberid,name,group,description,amount,force)
    else:
        raise RuntimeError('Invalid payment module')

def _isFutureDate(datestr):
   try:
      d = datetime.datetime.strptime(datestr,"%Y-%m-%dT%H:%M:%SZ")
      if (d > datetime.datetime.today()):
         return True
      else:
         return False
   except:
         logger.error("Date parsing exception for date %s" % datestr)
         return False

def _selfTest():
    if testPaymentSystems():
        for module in config.payments['modules'].split(","):
            logger.info("Payment System is Active, module is %s" % module)
            subs = getSubscriptions(module)
            logger.info("Subscriptions: %d" % len(subs))
            fsubs = filterSubscriptions(subs)
            validsubs = len(fsubs['valid'])
            inactive = len(fsubs['err_expired'])
            active = validsubs - inactive
            logger.info("VALID SUBSCRIPTIONS (TOTAL): %d" % validsubs)
            logger.info(" Active: %d  Inactive: %d" % (active,inactive))
            logger.info("Sanity check:: ERR_EMAIL: %d" % len(fsubs['err_email']))
            logger.info("Sanity check:: ERR_PLAN: %d" % len(fsubs['err_plan']))
            logger.info("Sanity check:: ERR_USERID: %d" % len(fsubs['err_userid']))
            logger.info("Sanity check:: ERR_EXPIRED: %d" % len(fsubs['err_expired']))

            writeSubscribersTextfile(subs,"/tmp/subscriptions.txt")
            writeSubscribersTextfile(fsubs['err_email'],'/tmp/err_email.txt')
            writeSubscribersTextfile(fsubs['err_userid'],'/tmp/err_userid.txt')
            writeSubscribersTextfile(fsubs['err_expired'],'/tmp/err_expired.txt')
            writeSubscribersTextfile(fsubs['err_plan'],'/tmp/err_plan.txt')
    else:
        logger.error("Payment system is not responding")
        return False

def setupPaymentSystems():
    global setupDone
    if setupDone:
      return
    for module in config.payments['modules'].split(","):
        if module == 'pinpayments':
            logger.info("Pinpayments module enabled")
            pinpay.setupPinpayments()
        elif module == 'stripe':
            logger.info("Stripe module enabled")
            stripe_pay.setupStripe()
        else:
            raise RuntimeError('Invalid payment system used')
    setupDone = True

def clearPaymentData(module):
    if module in ['pinpayments','stripe']:
        logger.info("Clearing payment data for %s" % module)
        dbutil._clearPaymentData(module)
    else:
        logger.error("Invalid payment module specified")

def clearSubscriptionData(module):
    if module in ['pinpayments','stripe']:
        logger.info("Clearing subscription data for %s" % module)
        dbutil._clearSubscriptionData(module)
    else:
        logger.error("Invalid payment module specified")

def addSubscriptionData(subs,module):
    if module in ['pinpayments','stripe']:
        logger.info("Updating Subscription data with valid subscribers from %s" % module)
        dbutil._addSubscriptionData(subs,module)
    else:
        logger.error("Invalid payment module specified")

def updatePaymentData(modules=None):
    setupPaymentSystems()
    if modules is None:
        modules = config.payments['modules']
    for module in modules.split(","):
        logger.info("Module: %s" % module)
        subs = getSubscriptions(module)
        print """


        NOW WE HAVE PAY DATA


        """
        logger.info(subs)
        fsubs = filterSubscriptions(subs)
        logger.info(fsubs)
        # TODO - Make sure retrieval and filtering is working
        clearSubscriptionData(module)
        addSubscriptionData(fsubs['valid'],module)


## Call with python ./authserver.py --command updatepayments instead

def cli_updatepayments(cmd,**kwargs):
        setupPaymentSystems()
        #_selfTest()
        # Fee charging, until we fix it..
        # Bill S
        #pinpay.chargeFee('4658001','WorkspaceRental','Rental for Mar','Workspace',"0.01","yes")
        # Nat DONE
        #pinpay.chargeFee('18005','WorkspaceRental','Rental for June','Workspace',"160","yes")
        # Mark P DONE
        #pinpay.chargeFee('5689154616688640','WorkspaceRental','Rental for Apr','Workspace',"180","yes")
        # John W DONE
        #pinpay.chargeFee('5073368378245120','WorkspaceRental','Rental for June','Workspace',"120","yes")
        ## Bill Foss DONE
        #pinpay.chargeFee('4358001','WorkspaceRental','Rental for June','Workspace',"300","yes")
        # Adam Bastien DONE
        #pinpay.chargeFee('5668001','WorkspaceRental','Rental for June','Workspace',"120","yes")
        # Ian Cook 4 Weeks auto plot rental
        #pinpay.chargeFee('190001','AutoPlot','2 Weeks plot rental','Auto',"100","yes")
        #Craig Johnston for Battleship rental /1/2 space
        #pinpay.chargeFee('5689127638925312','WorkspaceRental','Rental for June','Workspace','37.50','yes')
        #
        updatePaymentData()
