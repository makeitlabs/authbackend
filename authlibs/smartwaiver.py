#!/usr/bin/env python
"""
This module handles Waiver signing information from 3rd party integrations, specifically SmartWaiver.

The parent module should expect to be able to call the following methods:

1) getWaivers(<dict>) - Return all waivers given an API key and optionally a waiverid to use as a marker

In common use:

When populating a database initially, pass just API key and get all waivers
    waiver_dict = {'api_key': <proper smartwaiver API key>}
    testSystem(waiver_dict)    # OPTIONAL
    getWaivers(waiver_dict) 
    
When updating a database to add newer waivers, pass the API key and the last waiverid currently stored
    waiver_dict = {'api_key': <proper smartwaiver API key>, 'waiver_id': <waiver id>}
    getWaivers(waiver_dict)

The API Key must be considered sensitive information and not stored in code or pulbic repositories.

In this example it is assumed that the tool calling this lib will handle loading the API key from
the appropriate storage location, as well as deal with storing the results as needed. A
temporary file (/tmp/waivers.xml) is kept for the last API call result to aid in debugging

"""

import pycurl
import urllib
import re
import xml.etree.ElementTree as ET
import ConfigParser
from StringIO import StringIO

baseuri = "https://www.smartwaiver.com/api/v3/"

def _getWaiversXML(api_key,waiverid):
    buffer = StringIO()
    c = pycurl.Curl()
    if waiverid is not None:
        uri = "%s?rest_request=%s&rest_asc&rest_since_waiverid=%s" % (baseuri,api_key,waiverid)
    else:
        uri = "%s?rest_request=%s&rest_asc" % (baseuri,api_key)
    print uri
    c.setopt(c.URL, uri)
    c.setopt(c.WRITEDATA,buffer)
    c.perform()
    c.close()
    body = buffer.getvalue()
    return body

def getWaivers(waiver_dict):
    members = list()
    more_members = True
    waiver_id = waiver_dict.get('waiver_id',None)
    xmlwaivers = _getWaiversXML(waiver_dict['api_key'],waiver_id)
    while more_members:
        f = open('/tmp/waivers.xml','w')
        f.write(xmlwaivers)
        f.close
        root = ET.fromstring(xmlwaivers)
        for child in root.iter('participant'):
            email = child.find('primary_email').text
            waiver_id = child.find('waiver_id').text
            firstname = child.find('firstname').text
            lastname = child.find('lastname').text
            created_date = child.find('date_created_utc').text
            m = {'email': email, 'waiver_id': waiver_id, 'firstname': firstname,
                 'lastname': lastname, 'created_date': created_date}
            members.append(m)
        more = root.find('more_participants_exist')
        if more is None:
            more_members = False
        else:
            print "More members... getting those after %s" % waiver_id
            xmlwaivers = _getWaiversXML(waiver_dict['api_key'],waiver_id)
    return members
    
def waiverXML():
    f = open('/tmp/waivers.xml','r')
    data = f.read();
    print data
    root = ET.fromstring(data)
    print root.tag
    for child in root.iter('participant'):
        print child.tag
        print child.find('primary_email').text
        print child.find('participant_id').text

if __name__ == "__main__":
    waiver_dict = {'api_key': '6acf8d5fd250853bff297078cfa7f9dc-292286'}
    waivers = getWaivers(waiver_dict)
    print waivers
    #waiverXML()

