#!/usr/bin/env python
# Utilities for MakeIt Labs

import hashlib
import string
import sqlite3
import re
from datetime import datetime,date
    
def hash_rfid(rfid):
    "Given an integer RFID, create a hashed value for storage"
    if rfid == 'None':
        return None
    else:
        try:
            m = hashlib.sha224()
            rfidStr = "%.10d"%(int(rfid))
            m.update(str(rfidStr).encode())
            return m.hexdigest()
        except:
            return None

def _utcTimestampToDatetime(ts):
    """Convert a UTC timestamp to my local time"""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")

def _safeemail(unsafe_str):
    """Sanitize email addresses strings used in some oeprations"""
    keepcharacters = ('.','_','@','-')
    return "".join(c for c in unsafe_str if c.isalnum() or c in keepcharacters).strip()

def _safestr(s):
    """Sanitize input strings used in some operations"""
    keepcharacters = ('-',' ','.')
    return "".join(c for c in s if c.isalnum() or c in keepcharacters).strip()

def _joinNameString(s):
    '''Replace all numerics and non-alphanumerics in a name string, then concatenate using . ''' 
    newstr = re.findall(r"[\w]+",s)
    #newid = m['name'].replace(" ",".")
    return ".".join(newstr)

def alertAdmins(severity,msg):
    '''Alert admins of an issue. Intended to be configurable for notification mechanisms'''
    pass

def nameToFirstLast(namestr):
    names = namestr.split(" ")
    first = names[0]
    last = " ".join(names[1:])
    return {'first': first, 'last': last}

            

