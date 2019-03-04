#!/usr/bin/python2
"""
vim:tabstop=2:expandtab
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

import argparse,os,sys
from authlibs.init import authbackend_init, createDefaultUsers


from sqlalchemy.exc import IntegrityError
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response
# NEwer login functionality
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from datetime import timedelta
from authlibs import utilities as authutil
from authlibs.db_models import db, ApiKey, Role, UserRoles, Member, Resource, MemberTag, AccessByMember, \
			Blacklist, Waiver, Subscription, Node, NodeConfig, Tool, KVopt
import json


import sqlite3
from flask import g

def connect_source_db():
    """Convenience method to connect to the globally-defined database"""
    con = sqlite3.connect("original.db",check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

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


def process_source_table(table,columns):
        coldata={}
        for x in columns:
                coldata[x]=0
        rows= query_source_db("select * from {0};".format(table))
        for (i,x) in enumerate(rows):
            # print i,x
            for (ii,y) in enumerate(x):
                if y and y != "":
                    coldata[columns[ii]]+=1

        print table, coldata,"Total Rows",len(rows)

def get_slack_users(args=()):
        try:
          slackdata=json.load(open(args.allusers))
        except:
            print """
    ***
    *** no allusers.txt - no Slack data imported
    ***
            """
            return {}
        slack_users={}
        discards=[]
        slack_email_to_users={}
        for x in slackdata['members']:
            u={}
            u['name']=x['name']
            if 'real_name' in x:
                #print x['name'],x['deleted'],x['is_app_user'],x['is_bot'],x['real_name']
                u['real_name']=x['real_name']
                #print u['real_name']
            else:
                #print x['name'],x['deleted'],x['is_app_user'],x['is_bot'],"NO REAL NAME"
                if 'real_name_normalized' in x:
                    #print x['real_name_normlized']
                    pass
                else:
                    #print "NO REAL NAME FOR",x['name']
                    pass
                pass
            if x['deleted']==False  and x['is_app_user']==False and x['is_bot'] == False and 'email' in x['profile']:
                u["email"]=x["profile"]["email"]
                if "first_name" in x['profile'] and "last_name" in x['profile']:
                    u["first_name"]=x["profile"]["first_name"]
                    u["last_name"]=x["profile"]["last_name"]
                else:
                    u["first_name"]=".".split(x["name"])[0].title()
                    u["last_name"]=".".split(x["name"])[-1].title()
                    u["first_name"]=x["name"].split(".")[0].title()
                    u["last_name"]=x["name"].split(".")[-1].title()
                u["phone"]=x["profile"]["phone"]
                u["real_name_normalized"]=x["profile"]["real_name_normalized"]
                u['name']=x['name']
                #print u['first_name'],u['last_name'],x['name']
                slack_users[x['name']]=u
                e = x['profile']['email']
                if e.lower().endswith('@makeitlabs.com'):
                    e=e.split("@")[0]
                    slack_email_to_users[e]=u['name']
            else:
                if 'email' not in x['profile']:
                    #print "ERROR",x['name'],"was not migrated NO EMAIL",
                    # These were all bots
                    pass
                else:
                    print "ERROR",x['name'],x['profile']['email'],"was not migrated"
                discards.append(x['name'])
            
        #print "DISCARDS",discards
        #print "IMPORTS",len(slack_users)
        #for x in slack_users:
        #    print x,slack_users[x]
        return slack_users,slack_email_to_users


def testdt(a):
    print a,authutil.parse_datetime(a)

def dttest():
    testdt("2018-01-02T03:04:05Z")
    testdt("2018-01-02 03:04:05")
    testdt("2018-01-02")
    testdt("Sat Jan 21 11:46:19 2017")
    
if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--overwrite",help="Overwrite entire database with migrated data")
    parser.add_argument("--testdt",help="Only test datetime functions",action="store_true")
    parser.add_argument("--testdata",help="Add test data to database",action="store_true")
    parser.add_argument("--newdata",help="Add new data to database",action="store_true")
    parser.add_argument("--noslack",help="Do not handle slack users",action="store_true")
    parser.add_argument("--nomigrate",help="Don't migrate data. Just create DB (and optionally add test data)",action="store_true")
    parser.add_argument("--allusers",help="Specify location of allusers.txt file",default="../allusers.txt")
    parser.add_argument("--explicit-slack-ids",help="Specify location of explicit_slack_ids.txt file",default="../explicit_slack_ids.txt")
    parser.add_argument("--unhashed-tags-all",help="Specify location of unhashed-tags-all.txt file",default="../unhashed-tags-all.txt")
    #(args,extras) = parser.parse_known_args(sys.argv[1:])
    args = parser.parse_args(sys.argv[1:])

    any_missing = False
    
    if not os.path.isfile(args.allusers):
        print(">>> WARNING: can't find allusers.txt file at %s" % args.allusers)
        any_missing = True

    if not os.path.isfile(args.explicit_slack_ids):
        print(">>> WARNING: can't find explicit_slack_ids.txt file at %s" % args.explicit_slack_ids)
        any_missing = True

    if not os.path.isfile(args.unhashed_tags_all):
        print(">>> WARNING: can't find unhashed_tags_all.txt file at %s" % args.unhashed_tags_all)
        any_missing = True

    if any_missing:
        print
        print(">>> PRESS CTRL-C NOW IF WANT TO RECTIFY THIS BEFORE IMPORT")
        time.sleep(5)
    
    if args.testdt:
        dttest()
        sys.exit(0)

    if args.overwrite:
        print """
        ******
        ****** WRITING DATABASE
        ******
        ****** I will overwrite your ENTIRE DATABASEes
        ******
        ****** PRESS CONTROL-C IF YOU DON'T WANT TO DESTROY IT!!!
        ******
        """
        SQLALCHEMY_DATABASE_URI = "sqlite:///"+args.overwrite
        if 'MIGRATE_OVERWRITE_NODELAY' not in os.environ:
          time.sleep(5)

    try:
      os.unlink(args.overwrite)
      os.unlink("log.db")
    except:
      pass
    
    """
    app = create_app()
    db.init_app(app)
    user_manager = UserManager(app, db, User)
    """
    app=authbackend_init(__name__)
    with app.app_context():
        # Extensions like Flask-SQLAlchemy now know what the "current" app
        # is while within this block. Therefore, you can now run........

        db.create_all()
        createDefaultUsers(app)

        if not args.nomigrate:
          print """ START DB MIGRATION """

          tables=[
          "accessbyid","logs","payments","waivers",
          "accessbymember","memberbycustomer","resources",
          "blacklist","members","subscriptions",
          "feespaid","members_Debug","tagsbymember"
          ]
          for t in tables:
              print "TABLE",t,"HAS", query_source_db("select COUNT(*) from {0};".format(t))[0][0],"ROWS"
                  
          membercols=[
              'member',
              'alt_email',
              'firstname',
              'lastname',
              'phone',
              'plan',
              'updated_date',
              'access_enabled',
              'access_reason',
              'active',
              'nickname',
              'name',
              'created_date']

          process_source_table("members",membercols)
          resource_cols=[
              'name',
              'description',
              'owneremail',
              'last_updated'
          ]
          process_source_table("resources",resource_cols)

          accessbymember_cols =[
                  'member',
                  'resource', 
                  'enabled',
                  'updated_date',
                  'level'
          ]
          process_source_table("accessbymember",accessbymember_cols)

          # CREATE TABLE accessbyid(resource,rfidtag,enabled,lastmodified);
          accessbyid_cols = [
              "resource","rfidtag","enabled","lastmodified"
          ]
          process_source_table("accessbyid",accessbyid_cols)

          # CREATE TABLE tagsbymember (member text, tagtype text, tagid text, updated_date text, tagname TEXT);
          tagsbymember_cols = [
              "member","tagtype","tagid","updated_date","tagname"
          ]
          process_source_table("tagsbymember",tagsbymember_cols)

                          

          """
              except BaseException as e:
                  print
                  print
                  print "ERROR",x['name'],str(e)
                  print
              """

          # Find odd slack users
          if not args.noslack:
              (su,slack_email_to_users) = get_slack_users(args)
              """
              for x in su:
                  vv=x.split(".")
                  if (len(vv)!=2): print x
              """

              # Members to Slack IDs


              slack_explicit_matches={}
              try:
                for x in open(args.explicit_slack_ids).readlines():
                    (a,b,c)=x.split()
                    slack_explicit_matches[b]=c
              except:
                  print """
              ***
              *** explicit_slac_id_.txt not found - not importing
              ***
                  """

          dbm = {}
          corrected_slack_ids={}
          mc = ",".join(membercols)

          members = query_source_db("select "+mc+" from members;")
          if not args.noslack:
              match = {
                      'no':0,
                      'exact':0,
                      'exact_email':0,
                      'nodelim':0,
                      'oddcase':0,
                      'odddelim':0,
                      'dotlast':0,
                      'firstonly':0,
                      'lastonly':0,
                      'firstlast':0,
                      'first0last':0,
                      'explicit':0,
              }
              for x in  members:
                  found = False
                  if x[0].lower() in slack_email_to_users:
                      match['exact_email']+=1
                      corrected_slack_ids[x[0]]=slack_email_to_users[x[0].lower()]
                      found=True
                  elif x[0] in su: 
                      match['exact']+=1
                      corrected_slack_ids[x[0]]=x[0]
                      found=True
                  else:
                      # case mismatch
                      for yy in su:
                          if yy.lower() == x[0].lower():
                              match['oddcase']+=1
                              corrected_slack_ids[x[0]]=yy
                              found=True
                  if not found:
                      first=x[0].split(".")[0].lower()
                      last=x[0].split(".")[-1].lower()
                      for yy in su:
                          slack_first = su[yy]['first_name'].lower()
                          slack_last = su[yy]['last_name'].lower()
                          if yy.lower() == first+last:
                              match['nodelim']+=1
                              corrected_slack_ids[x[0]]=yy
                              found=True
                          if yy.lower() == first+"_"+last:
                              match['odddelim']+=1
                              corrected_slack_ids[x[0]]=yy
                              found=True
                          if (slack_first.lower()==first.lower()) and (slack_last.lower()==last.lower()):
                              match['firstlast']+=1
                              #print "PROBABLY",x[0],yy
                              # found=True Than's Mike Sullivan :(
                          if yy.lower() == first[0]+"."+last:
                              #print "DOTLAST POSSIBLY",x[0],yy
                              match['dotlast']+=1
                          if yy.lower() == first:
                              #print "FIRSTONLY POSSIBLY",x[0],yy
                              match['firstonly']+=1
                          if yy.lower() == last:
                              #print "LASTONLY POSSIBLY",x[0],yy
                              match['lastonly']+=1
                          if yy.lower().endswith(last):
                              #print "POSSIBLY",x[0],yy
                              match['lastonly']+=1
                          if (slack_first[0]==first[0]) and (slack_last==last):
                              match['first0last']+=1
                              #print "POSSIBLY",x[0],yy
                  if x[0] in slack_explicit_matches:
                      match['explicit']+=1
                      print "CORRECTED ",x[0],"SLACK ID",slack_explicit_matches[x[0]]
                      corrected_slack_ids[x[0]]=slack_explicit_matches[x[0]]
                      found=True
                  if not found:
                      #print "No match for ",x[0]
                      match['no']+=1
                      
                      

              print "Slack: ",match
              print "Loaded ",len(corrected_slack_ids),"Slack IDs"
              

          ##
          ## Okay build new "member" table..
          ##

        
          for x in  members:
              slack=None
              if x[0] in corrected_slack_ids:
                  slack=corrected_slack_ids[x[0]]
              mem = Member()


              if slack:
                  first=su[slack]['first_name']
                  last=su[slack]['last_name']
                  #print x[0],slack,first,last
              else:
                  nm=x[0].split(".")

                  if len(nm)==2:
                      first = nm[0]
                      last = nm[1]
                  elif len(nm)==3:
                      print "WARNING-Check first/last for ",x[0],nm[0],nm[1],nm[2]
                      first=nm[0]
                      last=nm[1]+nm[2]
                  else:
                      print "WARNING-Check first/last for ",x[0]
                      first=""
                      last=""

              created=None
              if (x[12]):
                  created=authutil.parse_datetime(x[12])

                  mem.member = x[0]
                  mem.email = x[0]+"@makeitlabs.com"
                  mem.alt_email = x[1]
                  mem.firstname = first
                  mem.slack = slack
                  mem.lastname = last
                  mem.phone = x[4]
                  mem.plan = x[5]
                  if x[7] is None: mem.access_enabled = 1 
                  elif x[7]=="": mem.access_enabled = 1 
                  elif x[7]==0: mem.access_enabled = 0 
                  else:
                    print "ERROR - %s access_enabled is \"%s\" type %s" % (x[0],x[7],type(x[7]))
                    sys.exit (0)
                  mem.access_reason = x[8]
                  mem.active = x[9]
                  mem.nickname = first
                  mem.stripe_name = x[11]
                  mem.time_created = created
                  mem.email_confirmed_at=created
                  #print mem
                  #print x[0],x[1],first,last,x[4],x[5],x[6],x[7],x[8],x[9],x[10],x[11],created
             
                  if args.overwrite: db.session.add(mem)
          if args.overwrite: db.session.flush()
          if args.overwrite: db.session.commit()

          """
          mem.member = db.Column(db.String(50), unique=True)
          mem.email = db.Column(db.String(50))
          mem.alt_email = db.Column(db.String(50))
          mem.firstname = db.Column(db.String(50))
          mem.slack = db.Column(db.String(50))
          mem.lastname = db.Column(db.String(50))
          mem.phone = db.Column(db.String(50))
          mem.plan = db.Column(db.String(50))
          mem.updated_date = db.Column(db.DateTime())
          mem.access_enabled = db.Column(db.Integer())
          mem.access_reason = db.Column(db.String(50))
          mem.active = db.Column(db.Integer())
          mem.nickname = db.Column(db.String(50))
          mem.name = db.Column(db.String(50))
          mem.time_created = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
          mem.time_updated = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
          """
          #
          # RESOURCES
          #

          dbr = {}
          mc = ",".join(resource_cols)
          #print mc
          rez = query_source_db("select "+mc+" from resources;")

          for x in rez:
              #print x
              resources = Resource()
              resources.name = x[0]
              resources.description = x[1]
              resources.owneremail = x[2]
              #print resources
              if args.overwrite: db.session.add(resources)
          if args.overwrite: db.session.flush()
          if args.overwrite: db.session.commit()

          #
          # TAGS by member

          # Read decoded hashes
          byencoded={}
          try:
            for x in open(args.unhashed_tags_all).readlines():
                sp=x.strip().split()
                uid=sp[3]
                enc=sp[2]
                rawno=sp[1]
                byencoded[enc]=rawno
          except:
              print """
  ***
  *** ERROR: No decoded hash file found
  *** Tags IDs cannot be migrated
  ***
              """

          dbr = {}
          mc = ",".join(tagsbymember_cols)
          #print mc
          recs = query_source_db("select "+mc+" from tagsbymember;")

          # "member","tagtype","tagid","updated_date","tagname"
          good=0
          bad=0
          nounhash=0
          for x in recs:
              newtag = MemberTag()
              mid = Member.query.filter(Member.member==x[0]).first()
              newtag.member_id=None
              goodtag=False
              if mid:
                  newtag.member_id=mid.id
                  if x[2] in byencoded:
                    good+=1
                    newtag.tag_ident=byencoded[x[2]]
                    goodtag=True
                  else:
                    print "UNHASH LOOKUP FAILED FOR",x[2],x[0]
                    nounhash+=1
              else:
                  #print "NO RECORD FOR",x
                  bad+=1
              newtag.member=x[0]
              newtag.tag_type=x[1]
              #newtag.updated_date
              newtag.tag_name=x[4]
              lastupdate=authutil.parse_datetime(x[3])
              #print newtag,x,lastupdate
              if args.overwrite and goodtag: db.session.add(newtag)
          if args.overwrite: db.session.flush()
          if args.overwrite: db.session.commit()

          print "FOBs migrated",good,"failed",bad,"Not-Unhashable",nounhash

          ##
          ## AccessByMember
          ##

          # member
          # resource
          # enabled
          # updated_date
          # level
          mc = ",".join(accessbymember_cols)
          #print mc
          recs = query_source_db("select "+mc+" from accessbymember;")
          good=0
          dup=0
          bad=0
          for x in recs:
              #print "Access for ",x[0],x[1]
              acc = AccessByMember()
              mid = Member.query.filter(Member.member==x[0]).first()
              rid = Resource.query.filter(Resource.name==x[1]).first()
              if mid == None or rid == None:
                  #print "FAILED FOB",x,mid,rid
                  bad+=1
              else:
                  member_temp = mid.member
                  resource_temp = rid.name
                  resource_id = rid.id
                  member_id = mid.id
                  acc.member_id=member_id
                  acc.resource_id=resource_id
                  acc.enabled=x[2]
                  acc.level=0
                  acc.updated_date=x[3]
                  if args.overwrite: 
                      # See if it already exists
                      if AccessByMember.query.filter(AccessByMember.member_id == member_id).filter(AccessByMember.resource_id == resource_id).first() is not None:
                          print "DUPICATE",member_id,resource_id
                          dup+=1
                      else:
                          good+=1
                          db.session.add(acc)
          if args.overwrite: db.session.flush()
          if args.overwrite: db.session.commit()
      
          print "AccessByMember migrated",good,"failed",bad,"Duplicate (error)",dup


          ##
          ## Blacklist
          ##

          mc = ",".join(['entry','entrytype','reason','updated_date'])
          #print mc
          recs = query_source_db("select "+mc+" from blacklist;")
          for x in recs:
              #print x
              bl = Blacklist()
              bl.entry=x[0]
              bl.entrytype=x[1]
              bl.reason=x[2]
              bl.updated_date=authutil.parse_datetime(x[3])
              if args.overwrite: db.session.add(bl)
          if args.overwrite: db.session.flush()
          if args.overwrite: db.session.commit()

          ##
          ## Waivers
          ##

          mc = ",".join(['waiverid','firstname','lastname','email','created_date'])
          #print mc
          recs = query_source_db("select "+mc+" from waivers;")
          good=0
          bad=0
          for x in recs:
              mid = Member.query.filter(Member.firstname==x[1]).filter(Member.lastname==x[2]).first()
              w = Waiver()
              if mid:
                  #print "FOUND MATCH",mid.firstname,mid.lastname,x[1],x[2]
                  #print "FOUND MATCH",mid.firstname,mid.lastname,x[1],x[2],mid.id
                  #print "AADD ID",mid.id
                  w.member_id=mid.id
                  good+=1
              else:
                  bad+=1
              w.firstname=x[1]
              w.lastname=x[2]
              w.waiver_id=x[0]
              w.email=x[3]
              w.created_date= authutil.parse_datetime(x[4])
              found=False
              if args.overwrite: db.session.add(w)
          if args.overwrite: db.session.flush()
          if args.overwrite: db.session.commit()

          door = Resource.query.filter(Resource.name=="frontdoor").one()
          door.info_text = "You have a valid membership, but you must complete orientation for access. Orientation is every Thursday at 7pm, or contact board@makeitlabs to schedule a convenient time"

          # Add default admins

          admin_id = Role.query.filter(Role.name=="Admin").one().id
          for mem in ("Adam.Shrey","Brad.Goodman","Bradley.Goodman","Steve.Richardson","Bill.Schongar"):
            m = Member.query.filter(Member.member==mem).one_or_none()
            if m:
              db.session.add(UserRoles(member_id=m.id,role_id=admin_id))

          db.session.commit()

          print "waivers migrated",good,"nomatches",bad


          print """ END DB MIGRATION """

    if args.newdata:
          res=Resource(name="laser-rabbit",description="80-Watt Rabbit laser", owneremail="laser@makeitlabs.com")
          db.session.add(res)
          db.session.flush() # Need to get ID from created thing
          db.session.add(Tool(name="laser-rabbit",resource_id=res.id))

    if args.testdata:
      print """***\n***Adding Test Data\n***\n"""
        #os.system("sqlite3 "+args.overwrite+" < test/testdata.sql")
      with app.app_context():
          # Extensions like Flask-SQLAlchemy now know what the "current" app
          # is while within this block. Therefore, you can now run........

          # Create default admin role and user if not present
          member = Member(member="admin", email='admin@makeitlabs.com',
              password=app.user_manager.hash_password("admin"),
              active="true",email_confirmed_at=datetime.utcnow())
          db.session.add(member)
          member.roles.append(Role.query.filter(Role.name=='Admin').one())

          member = Member(member="finance", email='finance@makeitlabs.com',
              password=app.user_manager.hash_password("finance"),
              active="true",email_confirmed_at=datetime.utcnow())
          db.session.add(member)
          member.roles.append(Role.query.filter(Role.name=='Finance').one())

          member = Member(member="ratt", email='ratt@makeitlabs.com',
              password=app.user_manager.hash_password("ratt"),
              active="true",email_confirmed_at=datetime.utcnow())
          db.session.add(member)
          member.roles.append(Role.query.filter(Role.name=='RATT').one())

          member = Member(member="useredit", email='useredit@makeitlabs.com',
              password=app.user_manager.hash_password("useredit"),
              active="true",email_confirmed_at=datetime.utcnow())
          db.session.add(member)
          member.roles.append(Role.query.filter(Role.name=='Useredit').one())

          member = Member(member="noprivs",email='noprivs@makeitlabs.com',
              password=app.user_manager.hash_password("noprivs"),
              active="true",email_confirmed_at=datetime.utcnow())
          db.session.add(member)

          member = Member(member="testrm",email='testrm@makeitlabs.com',
              password=app.user_manager.hash_password("testrm"),
              active="true",email_confirmed_at=datetime.utcnow())
          db.session.add(member)

          member = Member(member="testarm",email='testarm@makeitlabs.com',
              password=app.user_manager.hash_password("testarm"),
              active="true",email_confirmed_at=datetime.utcnow())
          db.session.add(member)

          member = Member(member="testtrainer",email='testtrainer@makeitlabs.com',
              password=app.user_manager.hash_password("testtrainer"),
              active="true",email_confirmed_at=datetime.utcnow())
          db.session.add(member)

          member = Member(member="testuser",email='testuser@makeitlabs.com',
              password=app.user_manager.hash_password("testuser"),
              active="true",email_confirmed_at=datetime.utcnow())
          db.session.add(member)

          member = Member(member="inactive",email='inactive@makeitlabs.com',
              password=app.user_manager.hash_password("inactive"),email_confirmed_at=datetime.utcnow())
          db.session.add(member)

          member = Member(member="unconfirmed",email='unconfirmed@makeitlabs.com',
              active="true",email_confirmed_at=datetime.utcnow(),
              password=app.user_manager.hash_password("unconfirmed"))
          db.session.add(member)

          member = Member(id=5000,member="Testy.Testerson",email='Testy.Testerson@makeitlabs.com',
              alt_email="testy@example.com",firstname="Testy",lastname="Testerson",slack="testy.testerson",
              access_enabled=1,active=1,
              email_confirmed_at=datetime.utcnow())
          db.session.add(member)

          member = Member(id=5001,member="First.User",email='First.User@makeitlabs.com',
              alt_email="fu@example.com",firstname="First",lastname="User",slack="first.user",
              access_enabled=1,active=1,
              email_confirmed_at=datetime.utcnow())
          db.session.add(member)

          member = Member(id=5002,member="bill.tester",email='bill.tester@makeitlabs.com',
              alt_email="billy@example.com",firstname="Bill",lastname="Tester",slack="bill.tester",
              access_enabled=1,active=1,
              email_confirmed_at=datetime.utcnow(),
              password=app.user_manager.hash_password("password"))
          db.session.add(member)

          member = Member(id=5003,member="Example.McTester",email='Example.McTester@makeitlabs.com',
              alt_email="emt@example.com",firstname="Example",lastname="McTester",slack="emtester",
              access_enabled=1,active=1,
              email_confirmed_at=datetime.utcnow(),
              password=app.user_manager.hash_password("password"))
          db.session.add(member)

          member = Member(id=5004,member="Oldy.McOldold",email='old.old@makeitlabs.com',
              alt_email="oldguy@example.com",firstname="Oldy",lastname="McOldOld",slack="oldy",
              access_enabled=1,active=1,
              email_confirmed_at=datetime.utcnow(),
              password=app.user_manager.hash_password("password"))
          db.session.add(member)

          db.session.add(MemberTag(id=5900,tag_ident="1110001111",tag_name="testfob",tag_type="rfid",member_id=5000))
          db.session.add(MemberTag(id=5901,tag_ident="1111111122",tag_name="testfob",tag_type="rfid",member_id=5001))
          db.session.add(MemberTag(id=5902,tag_ident="2222222222",tag_name="testfob",tag_type="rfid",member_id=5002))
          db.session.add(MemberTag(id=5903,tag_ident="1212121212",tag_name="testfob",tag_type="rfid",member_id=5003))
          db.session.add(MemberTag(id=5904,tag_ident="4545454545",tag_name="testfob",tag_type="rfid",member_id=5004))

          db.session.add(Waiver(firstname="Testy",lastname="Testerson",email="testy@example.com",member_id=5000))
          db.session.add(Waiver(firstname="First",lastname="User",email="fu@example.com"))
          db.session.add(Waiver(firstname="Mc",lastname="Gyber",email="mcg@example.com"))


          apikey = ApiKey(name="testkey",username="testkey",
              password=app.user_manager.hash_password("testkey"))
          db.session.add(apikey)

          ## Fake Payment Data
          # Will expire soon
          sub = Subscription(paysystem="stripe", subid="test_5000", customerid="cus_test", name="Testy Testerson",
                  email="test@example.com", plan="pro",expires_date=datetime.now()-timedelta(days=8),member_id=5000,active=1,membership="stripe:test:5000")
          db.session.add(sub)

          # Expired
          sub = Subscription(paysystem="stripe", subid="test_5002", customerid="cus_test2", name="William Tester",
                  email="tester@foo.com", plan="pro",expires_date=datetime.now()-timedelta(days=30),member_id=5002,active=1,membership="stripe:test:5002")
          db.session.add(sub)

          # Current (No expiration)
          sub = Subscription(paysystem="stripe", subid="test_5003", customerid="cus_test3", name="William Tester",
                  email="tester@foo.com", plan="pro",member_id=5003,active=1,membership="stripe:test:5003")
          db.session.add(sub)

          # 5003 - Example McTester has no sub data at all

          # Expires Soon
          sub = Subscription(paysystem="stripe", subid="test_5004", customerid="cus_test4", name="O Mcooldold",
                  email="oldy.mcold@foo.com", plan="pro",expires_date=datetime.now()+timedelta(days=6),member_id=5004,active=1,membership="stripe:test:5004")
          db.session.add(sub)

          node = Node(id=5000,name="node1",mac="001122334455")
          db.session.add(node)
          node = Node(id=5001,name="node2",mac="111111111111")
          db.session.add(node)

          db.session.add(Tool(id=5000,name="TestTool",node_id=5000,resource_id=5000))

          db.session.add(KVopt(id=5000,keyname="test1.Option1",description="Anything"))
          db.session.add(KVopt(id=5001,keyname="test1.Option2",kind="integer",description="Integer only"))
          db.session.add(KVopt(id=5002,keyname="test1.Option3.first"))
          db.session.add(KVopt(id=5005,keyname="test1.Option3.second"))
          db.session.add(KVopt(id=5006,keyname="test1.Option3.third"))
          db.session.add(KVopt(id=5003,keyname="test2.Option4",options="red;green;blue;chartruse",description="Your favorite color"))
          db.session.add(KVopt(id=5004,keyname="test2.season",default="summer",options="spring;summer;winter;fall",description="A nice season"))

          db.session.flush()

          db.session.add(NodeConfig(id=5000,node_id=5000,key_id=5000,value="val1"))
          db.session.add(NodeConfig(id=5001,node_id=5000,key_id=5001,value="val2"))
          db.session.add(NodeConfig(id=5002,node_id=5000,key_id=5003,value="green"))
          db.session.add(NodeConfig(id=5003,node_id=5001,key_id=5000,value="val1"))
          db.session.add(NodeConfig(id=5004,node_id=5001,key_id=5001,value="val2"))
          db.session.add(NodeConfig(id=5005,node_id=5001,key_id=5004,value="winter"))

          db.session.flush()

          res=Resource(id=5000,name="TestResource",description="Test Resource",
            slack_chan="#test-resource",slack_admin_chan="#test-resource-admins",owneremail="test@makeitlabs.com")
          db.session.add(res)
          res=Resource(id=5001,name="OtherTest",description="Another Test Resource",owneremail="test@makeitlabs.com")
          db.session.add(res)

          if args.nomigrate:
              # Since we don't have any other data in here - create a "frontdoor" entry
              res=Resource(id=1,name="frontfoor",description="Building Access",owneremail="board@makeitlabs.com")
              db.session.add(res)
              res=Resource(name="laser",description="Rabbit 80-watt",owneremail="laser@makeitlabs.com")
              db.session.add(res)
              res=Resource(name="fullspectrum",description="Full Spectrum 80-watt laser",owneremail="laser@makeitlabs.com")
              db.session.add(res)
              res=Resource(name="autolift",description="Auto lift",owneremail="lift@makeitlabs.com")
              db.session.add(res)

          db.session.flush()

          db.session.add(AccessByMember(member_id=5000,resource_id=1,active=True))
          db.session.add(AccessByMember(member_id=5001,resource_id=1,active=True))
          db.session.add(AccessByMember(member_id=5002,resource_id=1,active=True))
          db.session.add(AccessByMember(member_id=5004,resource_id=1,active=True))
          db.session.add(AccessByMember(member_id=5000,resource_id=5001,active=True))
          db.session.add(AccessByMember(member_id=5001,resource_id=5000,active=True))

          db.session.flush()

          # Set privileges for test accounts on test resource
          testrm = Member.query.filter(Member.member == "testrm").one().id
          db.session.add(AccessByMember(member_id=testrm,resource_id=5000,active=True,level=3))
          testarm = Member.query.filter(Member.member == "testarm").one().id
          db.session.add(AccessByMember(member_id=testarm,resource_id=5000,active=True,level=2))
          testtrainer = Member.query.filter(Member.member == "testtrainer").one().id
          db.session.add(AccessByMember(member_id=testtrainer,resource_id=5000,active=True,level=1))
          testuser = Member.query.filter(Member.member == "testuser").one().id
          db.session.add(AccessByMember(member_id=testuser,resource_id=5000,active=True,level=0))

          db.session.commit()
          print """***\n***Test Data Added\n***\n"""

    print "SUCCESS! You may also want to update pay and waiver data with:"
    print "curl http://testkey:testkey@localhost:5000/api/cron/nightly"

    if not args.overwrite:
        print """
        ******
        ****** WRITING DATABASE WAS DISABLED
        ******
        """

