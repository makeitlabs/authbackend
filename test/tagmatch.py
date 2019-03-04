#!/usr/bin/python2
"""
vim:tabstop=4:expandtab

This will generate the unhashed_user_tags.txt file

(Which you probably don't need)


"""

import argparse,os
from sqlalchemy.exc import IntegrityError
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response
# NEwer login functionality
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from flask_sqlalchemy import SQLAlchemy
#; older login functionality
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from contextlib import closing
import pytz
import json
import pycurl, sys
import ConfigParser
import xml.etree.ElementTree as ET
from StringIO import StringIO
from authlibs import utilities as authutil
from authlibs import payments as pay
from authlibs import smartwaiver as waiver
from authlibs import google_admin as google
from authlibs import membership as membership
from functools import wraps
import logging
logging.basicConfig(stream=sys.stderr)
import pprint
import paho.mqtt.publish as mqtt_pub
from datetime import datetime
from authlibs.db_models import db, User, Role, UserRoles, Member, Resource, MemberTag, AccessByMember, Blacklist, Waiver

# Load general configuration from file
defaults = {'ServerPort': 5000, 'ServerHost': '127.0.0.1'}
Config = ConfigParser.ConfigParser(defaults)
Config.read('makeit.ini')
ServerHost = Config.get('General','ServerHost')
ServerPort = Config.getint('General','ServerPort')
Database = Config.get('General','Database')
AdminUser = Config.get('General','AdminUser')
AdminPasswd = Config.get('General','AdminPassword')
DeployType = Config.get('General','Deployment')
DEBUG = Config.getboolean('General','Debug')

# Flask-User Settings
USER_APP_NAME = 'Basic'
USER_PASSLIB_CRYPTCONTEXT_SCHEMES=['bcrypt']
# Don;t want to include these, but it depends on them, so..
USER_ENABLE_EMAIL = True        # Enable email authentication
USER_ENABLE_USERNAME = False    # Disable username authentication
USER_EMAIL_SENDER_NAME = USER_APP_NAME
USER_EMAIL_SENDER_EMAIL = "noreply@example.com"

# SQLAlchemy setting
SQLALCHEMY_DATABASE_URI = "sqlite:///"+Database
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Load Waiver system data from file
waiversystem = {}
waiversystem['Apikey'] = Config.get('Smartwaiver','Apikey')

def create_app():
    # App setup
    app = Flask(__name__)
    app.config.from_object(__name__)
    app.secret_key = Config.get('General','SecretKey')
    return app

def safestr(unsafe_str):
    """Sanitize input strings used in some operations"""
    keepcharacters = ('_','-','.')
    return "".join(c for c in unsafe_str if c.isalnum() or c in keepcharacters).rstrip()

def safeemail(unsafe_str):
    """Sanitize email addresses strings used in some oeprations"""
    keepcharacters = ('.','_','@','-')
    return "".join(c for c in unsafe_str if c.isalnum() or c in keepcharacters).rstrip()

def init_db():
    """Initialize database from SQL schema file if needed"""
    with closing(connect_db()) as db:
        with app.open_resource('flaskr.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

"""
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect_db()
    return db
"""

def get_source_db():
    db = getattr(g, '_source_database', None)
    if db is None:
        db = g._source_database = connect_source_db()
    return db

def query_source_db(query, args=(), one=False):
    """Convenience method to execute a basic SQL query against the current DB. Returns a dict unless optional args used"""
    cur = get_source_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def query_db(query, args=(), one=False):
    """Convenience method to execute a basic SQL query against the current DB. Returns a dict unless optional args used"""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query):
    """Convenience method to execute a non-query SQL statement against the current DB."""
    cur = get_db().cursor()
    cur.execute(query)
    cur.close()


def parsedt(dt):
  tz=pytz.timezone("America/New_York")
  try:
    xx= datetime.strptime(dt,"%Y-%m-%dT%H:%M:%SZ")
    result = pytz.utc.localize(xx, is_dst=None).astimezone(tz).replace(tzinfo=None)
  except:
    try:
        result= datetime.strptime(dt,"%Y-%m-%d %H:%M:%S")
    except:
        # Sat Jan 21 11:46:19 2017
        try:
            result= datetime.strptime(dt,"%a %b %d %H:%M:%S %Y")
        except:
            result= datetime.strptime(dt,"%Y-%m-%d")
  return result

def testdt(a):
    print a,parsedt(a)

def dttest():
    testdt("2018-01-02T03:04:05Z")
    testdt("2018-01-02 03:04:05")
    testdt("2018-01-02")
    testdt("Sat Jan 21 11:46:19 2017")
    
if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--overwrite",help="Overwrite entire database with migrated data")
    parser.add_argument("--testdt",help="Only test datetime functions",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])


    decodes=[]
    byencoded={}
    for x in open("unhashed_tags_all.txt").readlines():
        sp=x.strip().split()
        uid=sp[3]
        enc=sp[2]
        rawno=sp[1]
        decodes.append({'member':uid,'encoded':enc,'decoded':rawno})
        byencoded[enc]=rawno
    
    
    app = create_app()
    db.init_app(app)
    user_manager = UserManager(app, db, User)
    with app.app_context():
        # Extensions like Flask-SQLAlchemy now know what the "current" app
        # is while within this block. Therefore, you can now run........

        tags = db.session.query(Member.member,Member.id,MemberTag.tag_id,MemberTag.tag_type,MemberTag.tag_name).filter(Member.id == MemberTag.member_id).all()
        good=0
        bad=0
        for x in tags:
            if x.tag_id in byencoded:
                good+=1
                print "FOUNDED",x.member,x.id,x.tag_id,x.tag_type,x.tag_name,byencoded[x.tag_id]
            else:
                print "UNKNOWN",x.member,x.id,x.tag_id,x.tag_type,x.tag_name
                bad += 1
            
        print "GOOD",good,"BAD",bad
