#!/usr/bin/env python
"""
This module handles Processing PinPayments information

The parent module should expect to call the following two methods:

1) testSystem() - Ensure the system is reachable and passes basic tests
2) getSubscribers() - Return a payment-system Independent JSON structure consisting of account data

"""

import ConfigParser
import sys
import pycurl
import re
import xml.etree.ElementTree as ET
import datetime
from StringIO import StringIO


DBTABLE = "pinpayments_data"
PINPAYDATA = ""
XMLMEMBERDATA = ""

def getSubscribersXML(paysystem):
   buffer = StringIO()
   c = pycurl.Curl()
   c.setopt(c.URL, paysystem['uri'])
   c.setopt(c.USERPWD, paysystem['token'] + ':X')
   c.setopt(c.WRITEDATA,buffer)
   c.perform()
   c.close()
   body = buffer.getvalue()
   return body

def _isReachable(uri) :
   print "Testing reachability"
   buffer = StringIO()
   c = pycurl.Curl()
   c.setopt(c.URL, uri)
   c.setopt(c.WRITEDATA,buffer)
   c.perform()
   status = "%d" % c.getinfo(c.RESPONSE_CODE)
   c.close()
   if re.match("4.*",status):
      return ({'success': False, 'error': '4xx Error code: %s' % status})
   else:
      return ({'success': True})
   
def testSystem(paysystem):
   """Perform basic checks on the Payment system to ensure we can reach it"""
   try:
      reachable = _isReachable(paysystem['rooturi'])
      return reachable['success']
   except:
      print "Exception"
      return False
   

# TODO: Make payment-system independent
def getSubscribersJSON(paysystem):
    """
    Get a payment system independent JSON structure with account data
    """
    try:
        xmlmembers = getSubscribersXML(paysystem)
        f = open('/tmp/subscribers.xml','w')
        f.write(xmlmembers)
        f.close
        root = ET.fromstring(xmlmembers)
        subscribers = list()
        noemail = list()
        notactive = list()
        for subscriber in root.findall('subscriber'):
            customerid = subscriber.find('customer-id').text
            #print ET.tostring(subscriber)
            firstname = subscriber.find('billing-first-name').text
            lastname = subscriber.find('billing-last-name').text
            sname = subscriber.find('screen-name').text
            # Filter known bad records with 'screen-name-for-<int>' syntax
            if not sname or sname.find('screen-name-for') > -1:
               continue
            email = subscriber.find('email').text
            plan = subscriber.find('subscription-plan-name').text
            expires = subscriber.find('active-until').text
            phone = subscriber.find('billing-phone-number').text
            if plan is None:
                membertype = None
            elif plan.find('Pro') > -1:
                membertype = 'pro'
            else:
                membertype = 'hobbyist'
            active = subscriber.find('active').text
            created = subscriber.find('created-at').text
            updated = subscriber.find('updated-at').text
            sub = {'customerid': customerid, 'firstname': firstname, 'lastname': lastname, 'userid': sname, 'email': email, 'membertype': membertype, 'active': active, 'created': created, 'updatedon': updated, 'expires': expires, 'phone': phone }
            subscribers.append(sub)
        return subscribers
    except:
        raise




def _selfTest():
   # TEMP
   defaults = {}
   Config = ConfigParser.ConfigParser(defaults)
   Config.read('../makeit.ini')
   
   # Load Payment config from file
   paysystem = {}
   paysystem['valid'] = Config.getboolean('Pinpayments','Valid')
   paysystem['userid'] = Config.get('Pinpayments','Userid')
   paysystem['token'] = Config.get('Pinpayments','Token')
   paysystem['uri'] = Config.get('Pinpayments','Uri')
   paysystem['rooturi'] = Config.get('Pinpayments','RootURI')
   print paysystem
   testSystem(paysystem)
   subs = getSubscribersJSON(paysystem)
   print "NUMBER OF MEMBER RECORDS %d" % len(subs)
   return subs

   
if __name__ == "__main__":
   
   _selfTest()
