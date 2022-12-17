#!/usr/bin/env python
#vim:tabstop=2:expandtab
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

import urllib 
import re
import xml.etree.ElementTree as ET
import configparser
from .db_models import db, Waiver
#from StringIO import StringIO
import json
from flask import current_app
import datetime

from .templateCommon import *

baseuri = "https://api.smartwaiver.com"

def _getWaiversJSON(api_key,waiverid,last_date):
		resp = []
		response = urllib.request.urlopen(baseuri+"/ping")
		html = response.read()
	
		headers = {'sw-api-key': api_key}

		params = "?sort=asc"
		if (last_date):
			#fromDts = (last_date.date()-datetime.timedelta(days=13)).isoformat()
			fromDts = (last_date.date()-datetime.timedelta(days=1)).isoformat()
			toDts = (datetime.datetime.now()+datetime.timedelta(days=2)).date().isoformat()
			params += "&fromDts={0}&toDts={1}".format(fromDts,toDts)
		#params += "&fromDts={0}".format(fromDts)
		#print "PARAMS",params
		
		req = urllib.request.Request(baseuri+"/v4/search"+params, None, headers)
		response = urllib.request.urlopen(req)
		#the_page = response.read()
		j = json.load(response)
		#print json.dumps(j,indent=2)
		guid = j['search']["guid"]
		pages = j['search']['pages']
		#print "SEARCH GUID {0} PAGES {1}".format(guid,pages)

		for i in range(0,pages):
			req = urllib.request.Request(baseuri+"/v4/search/{0}/results?page={1}".format(guid,str(i)), None, headers)
			response = urllib.request.urlopen(req)
			j = json.load(response)
			for r in j['search_results']:
				#print "RESULT",r
				x = {
					'waiver_id':r['waiverId'],
					'date_created_utc':r['createdOn'],
					'primary_email':r['email'],
					'waiver_title':r['title'],
					'emergencyContactPhone':r['emergencyContactPhone'],
					'emergencyContactName':r['emergencyContactName']
				}
				for p in r['participants']:
					x['firstname']=p['firstName']
					x['lastname']=p['lastName']
					#print x
					resp.append(x)
			#print json.dumps(resp,indent=2)
			#print json.dumps(j,indent=2)
			#print "PAGES {0}".format(i,j);
			
		#print "RETURING WAIVERS",len(resp)
		return resp
		

def getWaivers(waiver_dict):
    members = list()
    more_members = True
    waiver_id = waiver_dict.get('waiver_id',None)
    last_date = waiver_dict.get('last_date',None)
    logger.debug ("Fetching waivers after %s" % last_date)
    try:
      jsonwaivers = _getWaiversJSON(waiver_dict['api_key'],waiver_id,last_date)
    except BaseException as e:
      logger.error ("Error fetching waivers {0}".format(str(e)))
      return
	
    for j in  jsonwaivers:
      email = j['primary_email']
      waiver_id = j['waiver_id']
      title = j['waiver_title']
      firstname = j['firstname']
      lastname = j['lastname']
      eContactName = j['emergencyContactName']
      eContactPhone = j['emergencyContactPhone']
      created_date = j['date_created_utc']
      m = {'email': email, 'waiver_id': waiver_id, 'firstname': firstname,'emergencyName':eContactName,'emergencyPhone':eContactPhone,
           'lastname': lastname, 'title': title, 'created_date': created_date}
      members.append(m)
    return members
    
def waiverXML():
    f = open('/tmp/waivers.xml','r')
    data = f.read();
    print (data)
    root = ET.fromstring(data)
    print (root.tag)
    for child in root.iter('participant'):
        print (child.tag)
        print (child.find('primary_email').text)
        print (child.find('participant_id').text)

def getLastWaiver():
    """Retrieve the most recently created (last) waiver from the database"""
    #sqlstr = "select waiverid from waivers order by created_date desc limit 1"
    #w = query_db(sqlstr,"",True)
    w = Waiver.query.order_by(Waiver.created_date.desc()).limit(1).one_or_none()
    if not w:
      return None
    return (w.waiver_id,w.created_date)


if __name__ == "__main__":
		print ("To do this, use:")
		print ("python ./authserver.py --command updatewaivers")

