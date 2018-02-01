#!/usr/bin/env python
"""
This module handles Processing PinPayments information

The parent module should expect to call the following two methods:

1) testSystem() - Ensure the system is reachable and passes basic tests
2) getSubscribers() - Return a payment-system Independent JSON structure consisting of account data

"""

import config

import sys
import pycurl
import re
import xml.etree.ElementTree as ET
from StringIO import StringIO
import utilities

import logging
logger = logging.getLogger(__name__)

def getSubscribersXML():
   logger.info("Getting Subscribers, may take 30+ seconds")
   buffer = StringIO()
   c = pycurl.Curl()
   c.setopt(c.URL, config.pinpayments['uri'])
   c.setopt(c.USERPWD, config.pinpayments['token'] + ':X')
   c.setopt(c.WRITEDATA,buffer)
   c.perform()
   c.close()
   body = buffer.getvalue()
   return body

def _sendCharge(uri,data):
   buffer = StringIO()
   c = pycurl.Curl()
   c.setopt(c.URL, uri)
   c.setopt(c.USERPWD, config.pinpayments['token'] + ':X')
   c.setopt(pycurl.POST, 1)
   c.setopt(pycurl.HTTPHEADER, ["Content-type: text/xml"])
   c.setopt(pycurl.POSTFIELDS, data)
   c.setopt(c.WRITEDATA,buffer)
   c.perform()
   status = c.getinfo(pycurl.HTTP_CODE)
   c.close()
   return status

def _isReachable(uri) :
   logger.info("Testing Pinpayments reachability")
   buffer = StringIO()
   c = pycurl.Curl()
   c.setopt(c.URL, uri)
   c.setopt(c.WRITEDATA,buffer)
   c.perform()
   status = "%d" % c.getinfo(c.RESPONSE_CODE)
   c.close()
   if re.match("4.*",status):
      logger.error("Pinpayments error code: %s " % status)
      return ({'success': False, 'error': '4xx Error code: %s' % status})
   else:
      logger.info("Pinpayments is reachable")
      return ({'success': True})
   

def testSystem():
   """Perform basic checks on the Payment system to ensure we can reach it"""
   try:
      reachable = _isReachable(config.pinpayments['rooturi'])
      return reachable['success']
   except:
      return False
   
def chargeFee(customerid,name,description,group,amount,force):
   """Add a one-time fee onto an account, such as a usage fee for equipment or a damages fee"""
   xmlfee = """<fee><name>%s</name><description>%s</description><group>%s</group><amount>%s</amount>
         <allow_non_recurring_subscriber>true</allow_non_recurring_subscriber></fee>""" % (name,description,group,amount)
   uri = config.pinpayments['rooturi'] + "/api/v4/" + config.pinpayments['userid'] + "/subscribers/" + customerid + "/fees.xml"
   print(uri)
   print(xmlfee)
   status = _sendCharge(uri,xmlfee)
   success = False
   if status == 201:
      success = True
   else:
      print("Error calling Pinpayments to charge fee")
   return ({'success': success})

# TODO: Make payment-system independent
def getSubscriptionsJSON():
    """
    Get a payment system independent JSON structure with subscription data
    """
    try:
        xmlmembers = getSubscribersXML()
        f = open('/tmp/subscribers.xml','w')
        f.write(xmlmembers)
        f.close
        root = ET.fromstring(xmlmembers)
        subscribers = list()
        noemail = list()
        notactive = list()
        for subscriber in root.findall('subscriber'):
            customerid = subscriber.find('customer-id').text
            sname = subscriber.find('screen-name').text
            # Filter known bad records with 'screen-name-for-<int>' syntax
            if not sname or sname.find('screen-name-for') > -1:
               continue
            # Already concatenated with a dot.. maintain dot
            mname = sname.replace("."," ")
            email = subscriber.find('email').text
            expires = subscriber.find('active-until').text
            phone = subscriber.find('billing-phone-number').text
            planname = subscriber.find('subscription-plan-name').text
            # Feature level of plan determines membership level - Pro/Hobbyist
            plan = subscriber.find('feature-level').text
            if plan is None:
               plantype = "none"
            elif plan == '1':
               plantype = 'pro'
            elif plan == '2':
               plantype = "hobbyist"
            else:
               plantype = 'unknown'
            active = subscriber.find('active').text
            created = subscriber.find('created-at').text
            updated = subscriber.find('updated-at').text
            sub = {'customerid': customerid, 'subid': customerid, 'name': mname, 'email': utilities._safeemail(email), 'planname': planname, 'plantype': plantype, 'active': active, 'created': created, 'updatedon': updated, 'expires': expires, 'phone': phone }
            subscribers.append(sub)
        return subscribers
    except:
        raise
   
def setupPinpayments():
   logger.info("Setting up Pinpayments")
   pass

def selftest():
    logger.info("Running Pinpayments selftest")
    testSystem()
    subs = getSubscribersXML()
    return True

if __name__ == "__main__":
   logging.basicConfig(stream=sys.stdout, level=logging.INFO)
   selftest()
