#!/usr/bin/env python
"""
Payment abstraction layer

This module is intended to load appropriate payment system-specific libs
and use them to complete Payment-related operations.

"""

import pinpayments as pinpay
import datetime
import ConfigParser

def testSystem(paydict):
    print paydict
    if paydict['module'] == 'pinpayments':
        print("Testing Pinpayments..")
        return pinpay.testSystem(paydict)
    else:
        raise RuntimeError('Invalid payment system used')

def getSubscribers(paysystem):
    """Call the appropriate payment system module to get subscribers in JSON format"""
    if paysystem['module'] == "pinpayments":
        return pinpay.getSubscribersJSON(paysystem)
    else:
        raise RuntimeError('Invalid payment system used')

def filterSubscribers(subscribers):
    """Filter JSON list of subscribers into categories (valid,err_(email|plan|expired)) based on rules"""
    noemail = list()
    notactive = list()
    noplan = list()
    nouserid = list()
    validsubs = list()
    for sub in subscribers:
        valid = True
        if not sub['email']:
            noemail.append(sub)
            valid = False
        if valid and not sub['membertype']:
            noplan.append(sub)
            valid = False
        if valid and not sub['userid']:
            nouserid.append(sub)
            valid = False
        if valid:
            if not _isFutureDate(sub['expires']):
                notactive.append(sub)
            validsubs.append(sub)
    return {'valid': validsubs, 'err_email': noemail, 'err_plan': noplan, 'err_expired': notactive, 'err_userid': nouserid}

def writeSubscribersTextfile(subs,filename):
    f = open(filename,'w')
    for sub in subs:
        print>>f, sub
    f.close()
    
def updatePaymentsTable(db,tablename):
     # TODO: Make this more flexible
   subs = pay.getSubscribers(paysystem)
   fsubs = pay.filterSubscribers(subs)
   _clearPaymentData('pinpayments')
   _addPaymentData(fsubs['valid'],'pinpayments')
   
   
def _isFutureDate(datestr):
   try:
      d = datetime.datetime.strptime(datestr,"%Y-%m-%dT%H:%M:%SZ")
      if (d > datetime.datetime.today()):
         return True
      else:
         return False
   except:
         print "EXCEPTION"
         return False

def connect_db():
   con = sqlite3.connect(Database)
   con.row_factory = sqlite3.Row
   return con

def _selfTest(paysystem):
    if testSystem(paysystem):
        print "Payment System is Active, module is %s" % paysystem['module']
        subs = getSubscribers(paysystem)
        print "Subscribers: %d" % len(subs)
        fsubs = filterSubscribers(subs)
        validsubs = len(fsubs['valid'])
        inactive = len(fsubs['err_expired'])
        active = validsubs - inactive
        print "VALID SUBSCRIBERS (TOTAL): %d" % validsubs
        print " Active: %d  Inactive: %d" % (active,inactive)
        print "Sanity check:: ERR_EMAIL: %d" % len(fsubs['err_email'])
        print "Sanity check:: ERR_PLAN: %d" % len(fsubs['err_plan'])
        print "Sanity check:: ERR_USERID: %d" % len(fsubs['err_userid'])
        print "Sanity check:: ERR_EXPIRED: %d" % len(fsubs['err_expired'])
       
        writeSubscribersTextfile(subs,"/tmp/subscribers.txt")
        writeSubscribersTextfile(fsubs['err_email'],'/tmp/err_email.txt')
        writeSubscribersTextfile(fsubs['err_userid'],'/tmp/err_userid.txt')
        writeSubscribersTextfile(fsubs['err_expired'],'/tmp/err_expired.txt')
        writeSubscribersTextfile(fsubs['err_plan'],'/tmp/err_plan.txt')
        return True
    else:
        print "Payment system is not responding"
        return False

if __name__ == "__main__":
     # TEMP
   defaults = {}
   Config = ConfigParser.ConfigParser(defaults)
   Config.read('../makeit.ini')
   
   # Load Payment config from file
   global paysystem
   paysystem = {}
   paysystem['module'] = "pinpayments"
   paysystem['valid'] = Config.getboolean('Pinpayments','Valid')
   paysystem['userid'] = Config.get('Pinpayments','Userid')
   paysystem['token'] = Config.get('Pinpayments','Token')
   paysystem['uri'] = Config.get('Pinpayments','Uri')
   paysystem['rooturi'] = Config.get('Pinpayments','RootURI')
   print paysystem
   _selfTest(paysystem)