"""
vim:tabstop=4:expandtab
MakeIt Labs Authorization System, v0.4
Author: bill.schongar@makeitlabs.com

A simple Flask-based system for managing Users, Resources and the relationships between them

Exposes both a UI as well as a few APIs for further integration.

Note: Currently all coded as procedural, rather than class-based because reasons. Deal.

TODO:
- Improved logging and error handling
- More input validation
- Check for any strings that need to be moved to INI file
- Consider Class-based approach
- Make more modular/streamlined
- Harden API security model (Allow OAuth, other?)
- More documentation
"""

import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response, Markup
# NEwer login functionality
from werkzeug.contrib.fixers import ProxyFix
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
#from flask_oauth import OAuth
from flask_login import logout_user, login_user
from authlibs import eventtypes
from flask_sqlalchemy import SQLAlchemy
#; older login functionality
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from contextlib import closing
import pycurl, sys
import ConfigParser
import xml.etree.ElementTree as ET
from StringIO import StringIO
from authlibs.init import authbackend_init, get_config, createDefaultUsers
from authlibs import cli
from authlibs import utilities as authutil
from authlibs import google_admin as google_admin
from authlibs import membership as membership
from functools import wraps
import logging
import pprint
import paho.mqtt.publish as mqtt_pub
from datetime import datetime
from authlibs.db_models import db, Role, UserRoles, Member, Resource, AccessByMember, Tool, Logs, UsageLog, Subscription, Waiver, MemberTag, ApiKey
import argparse
from flask_dance.contrib.google import  google 
from flask_dance.consumer import oauth_authorized

from authlibs.templateCommon import *
import google_oauth
from  authlibs import slackutils
from authlibs.main_menu import main_menu, index_page
""" GET PAGES"""

from authlibs.auth import auth
from authlibs.members import members
from authlibs.resources import resources as resource_pages
from authlibs.logs import logs as log_pages
from authlibs.waivers import waivers 
from authlibs.paylib import payments as paylib
from authlibs.api import api 
from authlibs.reports import reports 
from authlibs.tools import tools 
from authlibs.nodes import nodes 
from authlibs.kvopts import kvopts 
from authlibs.comments import comments 
from authlibs.apikeys import apikeys 
from authlibs.belog import belog

    

def create_app():
    # App setup
    app = Flask(__name__)
    app.config.from_object(__name__)
    app.secret_key = Config.get('General','SecretKey')
    return app


# Flask-Login use this to reload the user object from the user ID stored in the session

def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    if password == "" or password is None or not Member.query.filter_by(email=username,api_key=password).first():
        return False
    else:
        return True

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            return error_401()
        if not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


'''
DELETE
def connect_db():
    """Convenience method to connect to the globally-defined database"""
    con = sqlite3.connect(app.globalConfig.Database,check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def safestr(unsafe_str):
    """Sanitize input strings used in some operations"""
    keepcharacters = ('_','-','.','@')
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

def get_db():
    """Convenience method to get the current DB loaded by Flask, or connect to it if first access"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect_db()
    return db

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

def clearAccess(mid):
    """Remove all existing access permissions for a given, known safe member id"""
    sqlstr = "DELETE from accessbymember where member_id = (SELECT m.id FROM members m WHERE member='%s');" % mid
    execute_db(sqlstr)
    get_db().commit()

def addAccess(mid,access):
    """Add access permissions from a list for a given, known safe member id"""
    # perms = []
    # Member.query.filter(Member.member=="0").first()
    uid = Member.query.filter(Member.member==mid).with_entities(Member.id)
    for resource in access:
        #print("Adding %s for %s" % (resource,mid))
        acc = AccessByMember()
        acc.member_id=uid
        acc.resource_id = Resource.query.filter(Resource.name==resource).with_entities(Resource.id)
        db.session.add(acc)
    db.session.commit()
    db.session.flush()

    
    """
    cur = get_db().cursor()
    cur.executemany('INSERT into accessbymember (resource,member,enabled,updated_date) VALUES (?,?,?,?)', perms)
    get_db().commit()
    """

def expireMember(memberid):
    """Mark a user inactive due to expiration"""
    # TODO - Determine if we should "disable" user as well
    # TODO- Make a batch operation using a join?
    m = safestr(memberid)
    sqlstr = "update members set active='false' where member='%s'" % m
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def unexpireMember(memberid):
    """Mark a user active"""
    # TODO - Make this a batch operation?
    m = safestr(memberid)
    sqlstr = "update members set active='true' where member='%s'" % m
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def _expirationSync():
    """Make sure all expirations match what's in the Payments database"""
    sqlstr = "update members set active='true',updated_date=DATETIME('now') where member in (select member from payments where expires_date < date('now'))"
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()


def _clearPaymentData(paytype):
    """Remove all payment data for the configured paysystem type from the payments table"""
    sql = "delete from payments where paysystem= '%s'" % paytype
    execute_db(sql)
    get_db().commit()

def _addPaymentData(subs,paytype):
    """From a JSON list of subscribers, add entries to the Payments table"""
    users = []
    # TEMP - only blacklisting old, unpurgeable records for now
    blacklist = query_db("select entry from blacklist")
    bad = []
    for b in blacklist:
        bad.append(b['entry'])
    for sub in subs:
        if sub['customerid'] in bad:
            print "BLACKLIST: IGNORING CUSTOMERID %s for %s" % (sub['customerid'],sub['userid'])
        else:
            users.append((sub['userid'],sub['email'],'pinpayments',sub['membertype'],sub['customerid'],sub['created'],sub['expires'],sub['updatedon'],time.strftime("%c")))
    cur = get_db().cursor()
    cur.executemany('INSERT into payments (member,email,paysystem,plan,customerid,created_date,expires_date,updated_date,checked_date) VALUES (?,?,?,?,?,?,?,?,?)', users)
    get_db().commit()
    kick_backend()


def _deactivateMembers():
    """Mark all users as inactive, to ensure we catch any that have been removed from Payments table"""
    sqlstr = "update members set active='false', updated_date=Datetime('now')"
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def _syncMemberPlans():
    """Update Members table with currently paid-for plan from Payments"""
    sqlstr = """update members set plan = (select plan from payments where members.member=payments.member)
            where member in (select member from payments)"""
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def _activatePaidMembers():
    """Set users who are not expired to active state"""
    # This will be problematic if users somehow have two entries in payments- manual and other
    sqlstr = """update members set active='true', updated_date=Datetime('now')
            where member in (select member from payments where expires_date > Datetime('now'))"""
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def _updateMembersFromPayments(subs):
    """Bring Members table and up to date with latest user payment information. Requires Subscriber dict"""
    addMissingMembers(subs)
    _deactivateMembers()
    _syncMemberPlans()
    _activatePaidMembers()
    kick_backend()
    return True

def _updatePaymentsData():
    """Get the latest Payment system data and update Payments table. Return subscriber data structure."""
    for m in range:
      code

    subs = pay.getSubscriptions(paysystem)
    fsubs = pay.filterSubscribers(subs)
    _clearPaymentData('pinpayments')
    _addPaymentData(fsubs['valid'],'pinpayments')
    return fsubs
'''

########
# Request filters
########

'''
@app.before_request
def before_request():
	#g.db = connect_db()
    pass

# TODO : Change this to app.teardown_appcontext so we don't keep closing the DB? Ramifications?
@app.teardown_request
def teardown_request(exception):
	#db = getattr(g,'db',None)
	#if db is not None:
		#db.close()
    pass
'''

########
# Routes
########

def testdata():
    text="""
    From Reqest: {0}
    Name: {1} 
    Email: {2}
    Authenticated {3}
    Active {4}
    Anonymous {5}
    ID  {6}
    REMOMOTE_ADDDR  {7}
    HTTP_HOST  {8}
    """.format(request,current_user.member,current_user.email,current_user.is_authenticated,
            current_user.is_active,
            current_user.is_anonymous,
            current_user.get_id(),
            request.environ['REMOTE_ADDR'],
            request.environ['HTTP_HOST']
            )
    return text, 200, {'Content-type': 'text/plain'}
def create_routes():
    @app.route('/whoami')
    @app.route('/test/anyone')
    def TestAnyone():
        logger.debug("Debug test")
        logger.error("Error test")
        logger.info("Info test")
        logger.warning("Warning test")
        logger.critical("Critical test")
        return testdata()


    @app.route('/test/std')
    @login_required
    def TestStd():
        return testdata()

    @app.route('/test/oauth')
    #@google.authorization_required
    def TestOauth():
        return testdata()

    @app.route('/test/admin')
    @roles_required('Admin')
    def TestAdmin():
        return testdata()

    @app.route('/test/useredit')
    @roles_required(['Admin','Useredit'])
    def TestUseredit():
        return testdata()

    # THIS IS THE WRONG PAGE
    # Flask login uses /user/sign-in
    @app.route('/login')
    def login():
       if current_app.config['globalConfig'].DefaultLogin.lower() == "oauth":
         return redirect(url_for("google.login"))
       else:
         return render_template('login.html')

    @app.route('/locallogin')
    def locallogin():
       return render_template('login.html')

    # BKG LOGIN CHECK - when do we use thigs?
    # This is from old flask-login module??
    @app.route('/login/check', methods=['post'])
    def login_check():
        """Validate username and password from form against static credentials"""
        user = Member.query.filter(Member.member.ilike(request.form['username'])).one_or_none()
        if not user or not  user.password:
            # User has no password - make the use oauth
            return redirect(url_for('google.login'))
        if (user and current_app.user_manager.verify_password( request.form['password'],user.password)):
            login_user(user)
        else:
            flash('Username or password incorrect')
            return redirect(url_for('login'))

        return redirect(url_for('index'))

    @app.route('/logout')
    @login_required
    def logout():
       """Seriously? What do you think logout() does?"""
       logout_user()
       flash("Thanks for visiting, you've been logged out.")
       return redirect(url_for('login'))

    @app.route("/index")
    @app.route('/')
    @login_required
    def index():
       """Main page, redirects to login if needed"""
       return render_template('index.html',menu=index_page())

    #@app.before_request
    #def prerequest():
    #  print "HANDLE REQUEST",request.url

    @app.route('/search',methods=['GET','POST'])
    @login_required
    def search_members():
       """Takes input of searchstr from form, displays matching member list"""
       if 'searchstr' in request.form:
           searchstr = safestr(request.form['searchstr'])
       elif 'searchstr' in request.values:
           searchstr = safestr(request.values['searchstr'])

    
       members = membership.searchMembers(searchstr)
       return render_template('members.html',members=members,searchstr=searchstr)

    # resource is a DB model resource
    ### DEPREICATED TODO FIX BKG - Use one in "utiliteis"
    def getResourcePrivs(resource=None,member=None,resourcename=None,memberid=None):
        if resourcename:
            resource=Resource.query.filter(Resource.name==resourcename).one()
        if not member and not memberid:
            member=current_user
        p = AccessByMember.query.join(Resource,((Resource.id == resource.id) & (Resource.id == AccessByMember.resource_id))).join(Member,((AccessByMember.member_id == member.id) & (Member.id == member.id))).one_or_none()
        if p:
            return p.level
        else:
            return -1
        return 0



def init_db(app):
    # DB Models in db_models.py, init'd to SQLAlchemy
    db.init_app(app)

def has_no_empty_params(rule):
    defaults = rule.defaults if rule.defaults is not None else ()
    arguments = rule.arguments if rule.arguments is not None else ()
    return len(defaults) >= len(arguments)


def site_map(app):
    links = []
    for rule in app.url_map.iter_rules():
        # Filter out rules we can't navigate to in a browser
        print rule
        # and rules that require parameters


####
        
parser=argparse.ArgumentParser()
parser.add_argument("--createdb",help="Create new db if none exists",action="store_true")
parser.add_argument("--command",help="Special command",action="store_true")
(args,extras) = parser.parse_known_args(sys.argv[1:])

app=authbackend_init(__name__)


with app.app_context():
    # Extensions like Flask-SQLAlchemy now know what the "current" app
    # is while within this block. Therefore, you can now run........
    if (args.createdb):
        db.create_all()
        createDefaultUsers(app)
    try:
        db.session.query("* from test_database").all()
        app.jinja_env.globals['TESTDB'] = "YES"
    except:
        pass

    if app.config['globalConfig'].DeployType.lower() != "production":
        app.jinja_env.globals['DEPLOYTYPE'] = app.config['globalConfig'].DeployType
    if  args.command:
        cli.cli_command(extras,app=app,um=app.user_manager)
        sys.exit(0)

    # Register Pages
    
    authutil.kick_backend()
    create_routes()
    auth.register_pages(app)
    members.register_pages(app)
    resource_pages.register_pages(app)
    log_pages.register_pages(app)
    waivers.register_pages(app)
    api.register_pages(app)
    paylib.register_pages(app)
    reports.register_pages(app)
    nodes.register_pages(app)
    tools.register_pages(app)
    kvopts.register_pages(app)
    comments.register_pages(app)
    apikeys.register_pages(app)
    belog.register_pages(app)
    slackutils.create_routes(app)
    g.main_menu = main_menu
    app.config['main_menu'] = main_menu
    #print site_map(app)
    #app.login_manager.login_view="test"
    #print app.login_manager.login_view
    logger.info("STARTING")
    
# Start development web server
if __name__ == '__main__':
    app.run(host=app.config['globalConfig'].ServerHost, port=app.config['globalConfig'].ServerPort, debug=app.config['globalConfig'].Debug)
