import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash
from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from contextlib import closing
import pycurl, sys
import ConfigParser
import xml.etree.ElementTree as ET
from StringIO import StringIO
from authlibs import utilities as authutil
from authlibs import payments as pay
from json import dumps as json_dump

# Load general configuration from file
# TODO: Error handling
defaults = {'ServerPort': 5000, 'ServerHost': '127.0.0.1'}
Config = ConfigParser.ConfigParser(defaults)
Config.read('makeit.ini')
Database = Config.get('General','Database')
AdminUser = Config.get('General','AdminUser')
AdminPasswd = Config.get('General','AdminPassword')
DEBUG = Config.getboolean('General','Debug')
ServerHost = Config.get('General','ServerHost')
ServerPort = Config.getint('General','ServerPort')

# Load Payment config from file
paysystem = {}
paysystem['module'] = Config.get('Payments','Module')
paysystem['valid'] = Config.getboolean('Pinpayments','Valid')
paysystem['userid'] = Config.get('Pinpayments','Userid')
paysystem['token'] = Config.get('Pinpayments','Token')
paysystem['uri'] = Config.get('Pinpayments','Uri')
paysystem['rooturi'] = Config.get('Pinpayments','RootURI')


# App setup
app = Flask(__name__)
app.config.from_object(__name__)
app.secret_key = Config.get('General','SecretKey')

# Login mechanism, using Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class UserNotFoundError(Exception):
    pass

# Simple user class base on UserMixin
# TODO - DB-backed users
# http://flask-login.readthedocs.org/en/latest/_modules/flask/ext/login.html#UserMixin
class User(UserMixin):
    '''Simple User class'''
    USERS = {
        # username: password
        AdminUser: AdminPasswd,
        'bill': 'bubba'
    }

    def __init__(self, id):
        if not id in self.USERS:
            raise UserNotFoundError()
        self.id = id
        self.password = self.USERS[id]

    @classmethod
    def get(self_class, id):
        '''Return user instance of id, return None if not exist'''
        try:
            return self_class(id)
        except UserNotFoundError:
            return None
		 
# Flask-Login use this to reload the user object from the user ID stored in the session
@login_manager.user_loader
def load_user(id):
    return User.get(id)

def connect_db():
   con = sqlite3.connect(Database)
   con.row_factory = sqlite3.Row
   return con

def _safestr(unsafe_str):
	keepcharacters = (' ','.','_',',','-',"'")
	return "".join(c for c in unsafe_str if c.isalnum() or c in keepcharacters).rstrip()

def _safeemail(unsafe_str):
    keepcharacters = ('.','_','@','-')
    return "".join(c for c in unsafe_str if c.isalnum() or c in keepcharacters).rstrip()

def _isValidRFID(str):
   try:
	  temp = int(str)
	  sqlstr = "SELECT rfidtag from members where rfidtag = '%s'" % str
	  tags = query_db(sqlstr)
	  if len(tags) == 0:
		return True
	  else:
		 return False
   except:
	  return False

def init_db():
	with closing(connect_db()) as db:
		with app.open_resource('flaskr.sql', mode='r') as f:
			db.cursor().executescript(f.read())
		db.commit()
		
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect_db()
    return db

def query_db(query, args=(), one=False):
	cur = get_db().execute(query, args)
	rv = cur.fetchall()
	cur.close()
	return (rv[0] if rv else None) if one else rv

def execute_db(query):
	cur = get_db().cursor()
	cur.execute(query)
	cur.close()
	
def _clearAccess(mid):
    """Remove all existing access permissions for a given, safe member id"""
    sqlstr = "DELETE from accessbymember where member = '%s'" % mid
    execute_db(sqlstr)
    get_db().commit()

def _addAccess(mid,access):
    """Add access permissions from a list for a given, safe member id"""
    perms = []
    for resource in access:
        print "Adding %s for %s" % (resource,mid)
        perms.append((resource, mid, '1', time.strftime("%c")))
    print perms
    cur = get_db().cursor()
    cur.executemany('INSERT into accessbymember (resource,member,enabled,updated_date) VALUES (?,?,?,?)', perms)
    get_db().commit()

def _expireMember(memberid):
    """Mark a user inactive due to expiration"""
    # TODO - Determine if we should "disable" user as well
    # TODO- Make a batch operation using a join?
    m = _safestr(memberid)
    sqlstr = "update members set active=0 where member='%s'" % m
    execute_db(sqlstr)
    get_db().commit()
    
def _unexpireMember(memberid):
    """Mark a user active due to expiration"""
    # TODO - Make this a batch operation?
    m = _safestr(memberid)
    sqlstr = "update members set active=0 where member='%s'" % m
    execute_db(sqlstr)
    get_db().commit()
    
def _expirationSync():
    """Make sure all expirations match what's in the Payments database"""
    sqlstr = "update members set active='1',updated_date=DATETIME('now') where member in (select member from payments where expires_date < date('now'))"
    execute_db(sqlstr)
    get_db().commit()
    
def _createMember(m):
    """Add a member entry to the database"""
    sqlstr = "Select member from members where member = '%s'" % m['memberid']
    members = query_db(sqlstr)
    if members:
        return {'status': 'error','message':'That User ID already exists'}
    else:
        sqlstr = """insert into members (member,firstname,lastname,phone,plan,updated_date,access_enabled,active)
                    VALUES ('%s','%s','%s','%s','',DATETIME('now'),'0','0')
                 """ % (m['memberid'],m['firstname'],m['lastname'],m['phone'])
        execute_db(sqlstr)
        get_db().commit()
    return {'status':'success','message':'Member %s was created' % m['memberid']}

def _createResource(r):
    """Add a resource to the database"""
    sqlstr = """insert into resources (name,description,owneremail)
            values ('%s','%s','%s')""" % (r['name'],r['description'],r['owneremail'])
    execute_db(sqlstr)
    get_db().commit()
    #TODO: Catch errors, etc
    return {'status':'success','message':'Resource successfully added'}

def _setrfid(oldrfid,newrfid,id):
   if oldrfid == newrfid:
	  return True
   if _isValidRFID(newrfid) == False:
	  flash("Error: You must specify a valid RFID tag")
	  return False
   else:
	  sqlstr = "UPDATE members set rfidtag = '%s' where id = %d" % (newrfid,id)
	  print sqlstr
	  execute_db(sqlstr)
	  get_db().commit()
	  return True

def _get_resources():
	sqlstr = "SELECT name, owneremail, description from resources"
	return query_db(sqlstr)

def _clearPaymentData(paytype):
    """Remove all payment data for the configured paysystem type from the payments table"""
    sql = "delete from payments where paysystem= '%s'" % paytype
    execute_db(sql)
    get_db().commit()
    
def _addPaymentData(subs,paytype):
    """From a JSON list of subscribers, add entries to the Payments table"""
    users = []
    for sub in subs:
        users.append((sub['userid'],'pinpayments',sub['membertype'],sub['customerid'],sub['expires'],sub['updatedon'],time.strftime("%c")))
    cur = get_db().cursor()
    cur.executemany('INSERT into payments (member,paysystem,plan,customerid,expires_date,updated_date,checked_date) VALUES (?,?,?,?,?,?,?)', users)
    get_db().commit()
    
def _getResourceUsers(resource):
    """Given a Resource, return all users, their tags, and whether they are allowed or denied for the resource"""
    # Change to left join fo including ALL members and their tag ids, but iondicate allowed|notallowed by resoiurce
    sqlstr = """select m.member,t.tagid,t.tagname,m.plan,
            (case when coalesce(a.resource,'denied') != 'denied' then 'allowed' else 'denied' end) as allowed 
            from members m join tagsbymember t on t.member=m.member left outer join accessbymember a
            on m.member=a.member and a.resource='%s' group by t.tagid""" % resource
    print(sqlstr)
    users = query_db(sqlstr)
    return users

def _addMissingMembers():
    """Add to Members table any members in Payments but not in Members"""
    sqlstr = """insert into members (member,plan,updated_date) select p.member,p.plan,Datetime('now')
            from payments p left outer join members m on p.member=m.member where m.member is null"""
    execute_db(sqlstr)
    get_db().commit()
    
def _deactivateMembers():
    """Mark all users as inactive, to ensure we catch any that have been removed from Payments table"""
    sqlstr = "update members set active='false', updated_date=Datetime('now')"
    execute_db(sqlstr)
    get_db().commit()
    
def _syncMemberPlans():
    """Update Members table with currently paid-for plan from Payments"""
    sqlstr = """update members set plan = (select plan from payments where members.member=payments.member)
            where member in (select member from payments)"""
    execute_db(sqlstr)
    get_db().commit()
    
def _activatePaidMembers():
    """Set users who are not expired to active state"""
    # This will be problematic if users somehow have two entries in payments- manual and other
    sqlstr = """update members set active='true', updated_date=Datetime('now')
            where member in (select member from payments where expires_date > Datetime('now'))"""
    execute_db(sqlstr)
    get_db().commit()
    
def _updateMembersFromPayments():
    """Bring Members table and up to date with latest user payment information"""
    _addMissingMembers()
    _deactivateMembers()
    _syncMemberPlans()
    _activatePaidMembers()
    
def _updatePaymentsData():
    """Get the latest Payment information from the Payment system and update. Note: Members update is separate"""
    subs = pay.getSubscribers(paysystem)
    fsubs = pay.filterSubscribers(subs)
    _clearPaymentData('pinpayments')
    _addPaymentData(fsubs['valid'],'pinpayments')
    
########
# Request filters
########

@app.before_request
def before_request():
	g.db = connect_db()

# TODO : Change this to app.teardown_appcontext so we don't keep closing the DB? Ramifications?
@app.teardown_request
def teardown_request(exception):
	db = getattr(g,'db',None)
	if db is not None:
		db.close()

########
# Routes
########

@app.route('/login')
def login():
   return render_template('login.html')

@app.route('/login/check', methods=['post'])
def login_check():
    """Validate username and password from form against static credentials"""
    user = User.get(request.form['username'])
    if (user and user.password == request.form['password']):
        login_user(user)
    else:
        flash('Username or password incorrect')

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
   return render_template('index.html')
   
@app.route('/search',methods=['GET','POST'])
@login_required
def search_members():
   """Takes input of searchstr from form, displays matching member list"""
   searchstr = _safestr(request.form['searchstr'])
   safestr = "%" + searchstr + "%"
   sqlstr = "SELECT member as id, firstname, lastname, alt_email, active, plan, updated_date, access_enabled as enabled from members where firstname LIKE '%s' OR lastname LIKE '%s' OR member LIKE '%s'" % (safestr, safestr, safestr)
   members = query_db(sqlstr)
   return render_template('members.html',members=members,searchstr=searchstr)

# --------------------------------------
# Member viewing and editing functions
# Routes
#  /members : Show (HTTP GET - members()), Create new (HTTP POST - member_add())
#  /<memberid> - Show (HTTP GET - member_show()), Create new (HTTP POST - member_add())
#  /<memberid>/access - Show current access and interface to change (GET), Change access (POST)
#  /<memberid>/tags - Show tags associated with user (GET), Change tags (POST)
#  /<memberid>/edit - Show current user base info and interface to adjust (GET), Change existing user (POST)
# --------------------------------------

@app.route('/members', methods = ['GET'])
@login_required
def members():
	members = {}
	return render_template('members.html',members=members)

@app.route('/members', methods= ['POST'])
@login_required
def member_add():
    """Controller method for POST requests to add a user"""
    member = {}
    mandatory_fields = ['firstname','lastname','memberid']
    optional_fields = ['alt_email','phone']
    print request
    for f in mandatory_fields:
        member[f] = ''
        if f in request.form:
            member[f] = request.form[f]
        if member[f] == '':
            flash("Error: One or more mandatory fields not filled out")
            return redirect(url_for('members'))
    for f in optional_fields:
        member[f] = ''
        if f in request.form:
            member[f] = request.form[f]
    result = _createMember(member)
    if result['status'] == "success":
        return redirect(url_for('member_show',id=member['memberid']))
    else:
        flash(result['message'])
        return redirect(url_for('members'))

@app.route('/members/<string:id>/edit', methods = ['GET'])
@login_required
def member_edit(id):
    mid = _safestr(id)
    member = {}
    
    return "Show the user editing form now, then call member_update"
    
@app.route('/members/<string:id>', methods = ['GET'])
@login_required
def member_show(id):
   """Controller method to Display or modify a single user"""
   access = {}
   mid = _safestr(id)
   sqlstr = """select m.member, m.firstname, m.lastname, m.phone, m.updated_date, m.access_enabled,
            m.access_reason, m.active, m.alt_email, p.expires_date, p.plan, p.updated_date as payment_date
            from members m left join payments p on m.member=p.member where m.member='%s'""" % mid
   member = query_db(sqlstr,"",True)
   member = dict(member)
   sqlstr = """select r.description, a.updated_date from resources r left join accessbymember a
            on r.name=a.resource and a.member='%s' where a.enabled='1'""" % mid
   access = query_db(sqlstr)
   return render_template('member_show.html',member=member,access=access)
   
@app.route('/members/<string:id>/access', methods = ['GET'])
@login_required
def member_editaccess(id):
    """Controller method to display gather current access details for a member and display the editing interface"""
    mid = _safestr(id)
    sqlstr = "select tagid,tagtype from tagsbymember where member = '%s'" % mid
    tags = query_db(sqlstr)
    sqlstr = """select r.name,r.description,r.owneremail,a.member as id,a.enabled from resources r
            left join accessbymember a on r.name = a.resource AND a.member = '%s'""" % mid
    m = query_db(sqlstr)
    member = {}
    member['id'] = mid
    member['access']= m
    return render_template('member_access.html',member=member,tags=tags)

@app.route('/members/<string:id>/access', methods = ['POST'])
@login_required
def member_setaccess(id):
    """Controller method to receive POST and update user access"""
    mid = _safestr(id)
    access = {}
    for key in request.form:
        match = re.search(r"^access_(.+)",key)
        if match:
            access[match.group(1)] = 1
    _clearAccess(mid)
    _addAccess(mid,access)
    return redirect(url_for('member_editaccess',id=mid))
   
@app.route('/members/<string:id>/tags', methods = ['GET'])
@login_required
def member_tags(id):
    """Controller method to gather and display tags associated with a memberid"""
    mid = _safestr(id)
    sqlstr = "select tagid,tagtype,tagname from tagsbymember where member = '%s'" % mid
    tags = query_db(sqlstr)
    return render_template('member_tags.html',mid=mid,tags=tags)

@app.route('/members/<string:id>/tags', methods = ['POST'])
@login_required
def member_tagadd(id):
    """Controller method for POST to add tag for a user, making sure they are not duplicates"""
    mid = _safestr(id)
    ntag = _safestr(request.form['newtag'])
    htag = authutil.hash_rfid(ntag)
    if htag is None:
        flash("ERROR: The specified RFID tag is invalid, must be all-numeric")
    else:
        ntagtype = _safestr(request.form['newtagtype'])
        ntagname = _safestr(request.form['newtagname'])
        sqlstr = "select tagid from tagsbymember where tagid = '%s' and tagtype = '%s'" % (htag,ntagtype)
        etags = query_db(sqlstr)
        if not etags:
            sqlstr = """insert into tagsbymember (member,tagid,tagname,tagtype,updated_date)
                    values ('%s','%s','%s','%s',DATETIME('now'))""" % (mid,htag,ntagname,ntagtype)
            execute_db(sqlstr)
            get_db().commit()
            flash("Tag added.")
        else:
            flash("Error: That tag is already associated with a user")
    return redirect(url_for('member_tags',id=mid))
    

@app.route('/members/<string:id>/tags/delete/<string:tagid>', methods = ['GET'])
@login_required
def member_tagdelete(id,tagid):
    """Controller method for a non-API link (eg no HTTP DELETE) to Delete a tag that is associated with a user"""
    mid = _safestr(id)
    tid = _safestr(tagid)
    sqlstr = "delete from tagsbymember where tagid = '%s' and member = '%s'" % (tid,mid)
    execute_db(sqlstr)
    get_db().commit()
    flash("If that tag was associated with the current user, it was removed")
    return redirect(url_for('member_tags',id=mid))

# ----------------------------------------------------
# Resource management (not including member access)
# Routes:
#  /resources - View
#  /resources/<name> - Details for specific resource
#  /resources/<name>/access - Show access for resource
# ------------------------------------------------------

@app.route('/resources', methods=['GET'])
@login_required
def resources():
   """Controller method to Display resources"""
   resources = _get_resources()
   access = {}
   return render_template('resources.html',resources=resources,access=access,editable=True)

@app.route('/resources', methods=['POST'])
@login_required
def resource_create():
   """Controller method to Create (handle POST) a resource"""
   res = {}
   res['name'] = _safestr(request.form['rname'])
   res['description'] = _safestr(request.form['rdesc'])
   res['owneremail'] = _safeemail(request.form['rcontact'])
   result = _createResource(res)
   flash(result['message'])
   return redirect(url_for('resources'))

@app.route('/resources/<string:resource>', methods=['GET'])
@login_required
def resource_show(resource):
    print "FOOOOO"
    rname = _safestr(resource)
    sqlstr = "SELECT name, owneremail, description from resources where name = '%s'" % rname
    print sqlstr
    r = query_db(sqlstr,(),True)
    print r
    return render_template('resource_edit.html',resource=r)

@app.route('/resources/<string:resource>', methods=['POST'])
@login_required
def resource_update(resource):
    """Controller method to Update an existing resource via HTML form POST"""
    rname = _safestr(resource)
    rdesc = _safestr(request.form['rdescription'])
    remail = _safestr(request.form['remail'])
    sqlstr = "update resources set description='%s',owneremail='%s', last_updated=Datetime('now') where name='%s'" % (rdesc,remail,rname)
    execute_db(sqlstr)
    get_db().commit()
    flash("Resource updated")
    return redirect(url_for('resources'))

@app.route('/resources/<string:resource>/delete', methods=['POST'])
def resource_delete(resource):
    rname = _safestr(resource)
    sqlstr = "delete from resources where name='%s'" % rname
    execute_db(sqlstr)
    get_db().commit()
    flash("Resource deleted.")
    return redirect(url_for('resources'))

@app.route('/resources/<string:resource>/list', methods=['GET'])
def resource_showusers(resource):
    """Display users who are authorized to use this resource"""
    rid = _safestr(resource)
    sqlstr = "select member from accessbymember where resource='%s'" % rid
    authusers = query_db(sqlstr)
    return render_template('resource_users.html',resource=rid,users=authusers)
   
#TODO: Create safestring converter to replace string; converter?
@app.route('/resources/<string:resource>/log', methods=['GET','POST'])
def logging(resource):
   """Endpoint for a resource to log via API"""
   # TODO - verify resources against global list
   if request.method == 'POST':
    print "LOGGING FOR RESOURCE"
    # YYYY-MM-DD HH:MM:SS
    # TODO: Filter this for safety
    logdatetime = request.form['logdatetime']
    level = _safestr(request.form['level'])
    # 'system' for resource system, rfid for access messages
    userid = _safestr(request.form['userid'])
    msg = _safestr(request.form['msg'])
    sqlstr = "INSERT into logs (logdatetime,resource,level,userid,msg) VALUES ('%s','%s','%s','%s','%s')" % (logdatetime,resource,level,userid,msg)
    execute_db(sqlstr)
    get_db().commit()
    print "Committed"
    return render_template('logged.html')
   else:
    print "QUERYING LOGS FOR RESOURCE"
    if current_user.is_authenticated:
        r = _safestr(resource)
        sqlstr = "SELECT logdatetime,resource,level,userid,msg from logs where resource = '%s'" % r
        entries = query_db(sqlstr)
        return render_template('resource_log.html',entries=entries)
    else:
        abort(401)
        
        
# ------------------------------------------------
# Payments controllers
# Routes:
#  /payments - Show payments options
# ------------------------------------------------

@app.route('/payments', methods = ['GET'])
@login_required
def payments():
    """Controller method: Show payments options"""
    payments = {}
    sqlstr = "select MAX(checked_date) as checked from payments"
    cdate = query_db(sqlstr,(),True)
    return render_template('payments.html',cdate=cdate,payments=payments,paysystem=paysystem)

@app.route('/payments/manual', methods = ['GET'])
@login_required
def manual_payments():
   sqlstr = """select member,plan,expires_date,updated_date from payments where paysystem = 'manual'"""
   members = query_db(sqlstr)
   return render_template('payments_manual.html',members=members)


@app.route('/payments/manual/extend/<member>', methods = ['GET'])
@login_required
def payments_manual_extend(member):
    safe_id = _safestr(member)
    sqlstr = "update payments set expires_date=DATETIME(expires_date,'+31 days') where member = '%s' " % safe_id
    print(sqlstr)
    execute_db(sqlstr)
    get_db().commit()
    flash("Member %s was updated in the payments table" % safe_id)
    return redirect(url_for('manual_payments'))

@app.route('/payments/manual/expire/<member>', methods = ['GET'])
@login_required
def payments_manual_expire(member):
    safe_id = _safestr(member)
    sqlstr = "update payments set expires_date=datetime('now')  where member = '%s' " % safe_id
    execute_db(sqlstr)
    get_db().commit()
    # TODO: EXPIRE MEMBER FROM ACCESS CONTROLS
    flash("Member %s was forcibly expired" % safe_id)
    return redirect(url_for('manual_payments'))

@app.route('/payments/manual/delete/<member>', methods = ['GET'])
@login_required
def payments_manual_delete(member):
    safe_id = _safestr(member)
    sqlstr = "delete from payments where member = '%s' " % safe_id
    execute_db(sqlstr)
    get_db().commit()
     # TODO: EXPIRE MEMBER FROM ACCESS CONTROLS
    flash("Member %s was deleted from the payments table" % safe_id)
    return redirect(url_for('manual_payments'))
    
@app.route('/payments/test', methods = ['GET'])
@login_required
def test_payments():
   """Validate the payment system"""
   payments = {}
   if pay.testSystem(paysystem):
	  flash("Payment system is reachable.")
   else:
	  flash("Error: Payment system is UNreachable.")
   return redirect(url_for('payments'))

@app.route('/payments/update', methods = ['GET'])
@login_required
def update_payments():
    # TODO: return details/status/etc from each call for reporting
   _updatePaymentsData()
   _updateMembersFromPayments()
   flash("Payment data has just been updated, and members adjusted")
   return redirect(url_for('payments_show'))

@app.route('/payments/reports', methods = ['GET'])
@login_required
def payments_reports():
    f = request.args.get('filter','')
    sqlstr = "select * from payments"
    if f !='':
        if f == 'expired':
            sqlstr = sqlstr + " where expires_date < Datetime('now')"
        elif f == 'notexpired':
            sqlstr = sqlstr + " where expires_date > Datetime('now')"
        elif f == 'recentexpired':
            sqlstr = sqlstr + " where expires_date > Datetime('now','-180 days') AND expires_date < Datetime('now')"
        elif f == 'recentexpired':
            sqlstr = sqlstr + " where expires_date > Datetime('now','-180 days') AND expires_date < Datetime('now')"
    payments = query_db(sqlstr)
    return render_template('payments_reports.html',f=f,payments=payments)

# ------------------------------------------------------------
# Reporting controllers
# ------------------------------------------------------------

@app.route('/reports', methods=['GET'])
@login_required
def reports():
    return render_template('reports.html')
    

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

@app.route('/api/v1/members', methods=['GET'])
@login_required
def api_v1_members():
    sqlstr = "select m.member,m.plan,m.updated_date,p.expires_date from members m inner join payments p on m.member=p.member"
    outformat = request.args.get('output','json')
    filters = {}
    filters['active'] = _safestr(request.args.get('active',''))
    filters['access_enabled'] = _safestr(request.args.get('enabled',''))
    filters['expired'] = _safestr(request.args.get('expired',''))
    filters['plan'] = _safestr(request.args.get('plan',''))
    fstring = ""
    if len(filters) > 0:
        fstrings = []
        for f in filters:
            if f == 'active' or f == 'access_enabled':
                if filters[f] == "true" or filters[f] == "false":
                    fstrings.append("%s='%s'" % (f,filters[f]))
            if f == 'expired':
                if filters[f] == 'true':
                    fstrings.append("p.expires_date < Datetime('now')")
                if filters[f] == 'false':
                    fstrings.append("p.expires_date >= Datetime('now')")
            if f == 'plan':
                if filters[f] in ('pro','hobbyist'):
                    fstrings.append("m.plan='%s'" % filters[f])
        if len(fstrings) > 0:
            fstring = ' AND '.join(fstrings)
            sqlstr = sqlstr + " where " + fstring 
    print(sqlstr)
    members = query_db(sqlstr)
    output = ""
    jsonarr = []
    for m in members:
        if outformat == 'csv':
            output = output + "%s,%s,%s,%s\n" % (m['member'],m['plan'],m['updated_date'],m['expires_date'])
        elif outformat == 'json':
            jsonarr.append({'member':m['member'],'plan':m['plan'], 'updated_date': m['updated_date'], 'expires_date': m['expires_date']})
    if outformat == 'csv':
        ctype = "text/plain; charset=utf-8"
    elif outformat == 'json':
        ctype = "application/json"
        output = json_dump(jsonarr)
    return output, 200, {'Content-Type': '%s' % ctype, 'Content-Language': 'en'}

@app.route('/api/v1/members/<string:id>', methods=['GET'])
@login_required
def api_v1_showmember(id):
    mid = _safestr(id)
    outformat = request.args.get('output','json')
    sqlstr = """select m.member, m.plan, m.alt_email, m.firstname, m.lastname, m.phone, p.expires_date
            from members m inner join payments p on m.member=p.member where m.member='%s'""" % mid
    m = query_db(sqlstr,"",True)
    if outformat == 'json':
        output = {'member': m['member'],'plan': m['plan'],'alt_email': m['plan'],
                  'firstname': m['firstname'],'lastname': m['lastname'],
                  'phone': m['phone'],'expires_date': m['expires_date']}
        return json_dump(output), 200, {'Content-type': 'application/json'}
    
@app.route('/api/v1/resources/<string:id>/acl', methods=['GET'])
@login_required
def api_v1_show_resource_acl(id):
    rid = _safestr(id)
    users = _getResourceUsers(rid)
    outformat = request.args.get('output','csv')
    if outformat == 'csv':
        outstr = "member,allowed,tagid,tagname,plan"
        for u in users:
            outstr += "\n%s,%s,%s,%s,%s" % (u['member'],u['allowed'],u['tagid'],u['tagname'],u['plan'])
        return outstr, 200, {'Content-Type': 'text/plain', 'Content-Language': 'en'}
   
@app.route('/api/v1/logs/<string:id>', methods=['POST'])
@login_required
def api_v1_log_resource_create(id):
    rid = _safestr(id)
    entry = {}
    # Default all to blank, since needed for SQL
    for opt in ['event','timestamp','memberid','message','ip']:
        entry[opt] = ''
    for k in request.form:
        entry[k] = _safestr(request.form[k])
    return "work in progress"
    
    

if __name__ == '__main__':
    app.run(host=ServerHost,port=ServerPort)

