import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash
from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from contextlib import closing
import pycurl, sys
import ConfigParser
import xml.etree.ElementTree as ET
from StringIO import StringIO

# Load general configuration from file
# TODO: Error handling
Config = ConfigParser.ConfigParser()
Config.read('makeit.ini')
Database = Config.get('General','Database')
AdminUser = Config.get('General','AdminUser')
AdminPasswd = Config.get('General','AdminPassword')
DEBUG = Config.getboolean('General','Debug')
MEMBERDATA = {}


# Load Payment config from file
paysystem = {}
paysystem['valid'] = Config.getboolean('Payments','Valid')
paysystem['module'] = Config.get('Payments','Module')
paysystem['userid'] = Config.get('Payments','Userid')
paysystem['token'] = Config.get('Payments','Token')
paysystem['uri'] = Config.get('Payments','Uri')

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

def _safestr(str):
	removelist = "@_*;,"
	return re.sub(r'[^\w'+removelist+']','',str)

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
	
def _clear_permissions(rfid):
	sqlstr = "DELETE from accessbyid where rfidtag = '%s'" % rfid
	execute_db(sqlstr)
	get_db().commit()
	
def _add_permissions(rfid,access):
	perms = []
	for key in access:
	  print "Adding %s for %s" % (key,rfid)
	  perms.append((key, rfid, time.strftime("%c")))
	print perms
	cur = get_db().cursor()
	cur.executemany('INSERT into accessbyid (resource,rfidtag,lastmodified) VALUES (?,?,?)', perms)
	get_db().commit()
   
	  
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

def _call_pinpayments():
   buffer = StringIO()
   c = pycurl.Curl()
   c.setopt(c.URL, paysystem['uri'])
   c.setopt(c.USERPWD, paysystem['token'] + ':X')
   c.setopt(c.WRITEDATA,buffer)
   c.perform()
   c.close()
   body = buffer.getvalue()
   return body

def _test_payment_system():
   try:
	  MEMBERDATA = _call_pinpayments()
	  return True
   except:
      print "Unexpected error:", sys.exc_info()[0]
      return False

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
   sqlstr = "SELECT id, firstname, lastname, email, rfidtag, active, membertype, lastupdated, enabled from members where firstname LIKE '%s' OR lastname LIKE '%s' OR email LIKE '%s' OR rfidtag = '%s'" % (safestr, safestr, safestr, safestr)
   members = query_db(sqlstr)
   return render_template('members.html',members=members,searchstr=searchstr)

# Display Member-related controls, including:
# - Search for pattern and display matches
@app.route('/members', methods = ['GET','POST'])
@login_required
def members():
	members = {}
	return render_template('members.html',members=members)
   
# Allow update of common attributes such as RFID and access
@app.route('/members/<int:id>', methods = ['GET','POST'])
@login_required
def member(id):
   """Display or modify a single user"""
   access = {}
   sqlstr = "SELECT id, firstname, lastname, email, rfidtag, active, membertype, lastupdated, enabled from members where id = %d" % id
   member = query_db(sqlstr,"",True)
   member = dict(member)
   print "Member rfidtag: %s " % member['rfidtag']
   sqlstr = "SELECT name, owneremail, description from resources"
   resources = query_db(sqlstr)
   if request.method == 'POST':
	  newrfid = request.form['rfid']
	  oldrfid = member['rfidtag']
	  print "New rfid %s  old rfid %s " % (newrfid, oldrfid)
	  for key in request.form:
		 match = re.search(r"^access_(.+)",key)
		 if match:
			access[match.group(1)] = 1
	  if _setrfid(oldrfid,newrfid,id):
		 _clear_permissions(oldrfid)
		 _add_permissions(newrfid,access)
		 member['rfidtag'] = newrfid
		 flash("Member information updated")
	  else:
		 flash("NO changes made - RFID in use or invalid") 
	  
   sqlstr = "SELECT resource from accessbyid where rfidtag = '%s'" % member['rfidtag']
   access = query_db(sqlstr)
   print access
   accessDict = {}
   for entry in access:
	  accessDict[entry['resource']] = 1
   return render_template('edit_member2.html',member=member,resources=resources,access=accessDict)
   
   
@app.route('/resources')
@login_required
def resources():
   """Display or modify resources"""
   if request.method == 'POST':
	  addResource()
   elif request.method != 'GET':
	  flash("Error: Unsupported HTTP method")
   resources = _get_resources()
   access = {}
   return render_template('show_resources.html',resources=resources,access=access,editable=True)

#TODO: input validation
@app.route('/resources/<string:resource>', methods=['GET'])
@login_required
def one_resource(resource):
   sqlstr = "SELECT name, owneremail, description from resources where name = '%s'" % resource
   r = query_db(sqlstr,(),True)
   return render_template('edit_resource.html',resource=r)

@app.route('/resources/<string:resource>/list', methods=['GET'])
def accesslist(resource):
   sqlstr = """select accessbyid.rfidtag, members.firstname, members.lastname, members.membertype from accessbyid
   inner join members on members.rfidtag = accessbyid.rfidtag AND
   accessbyid.resource = '%s' GROUP BY accessbyid.rfidtag""" % resource
   users = query_db(sqlstr)
   return render_template('resource_acl.html',users=users)
   
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

@app.route('/payments', methods = ['GET'])
@login_required
def payments():
   payments = {}
   return render_template('payments.html',payments=payments,paysystem=paysystem)

@app.route('/payments/test', methods = ['GET'])
@login_required
def test_payments():
   """Validate the payment system"""
   payments = {}
   if _test_payment_system():
	  payments['valid'] = True
	  payments['memberdata'] = MEMBERDATA
   else:
	  payments['invalid'] = True
   return render_template('payments.html',payments=payments,paysystem=paysystem)

@app.route('/payments/update', methods = ['GET'])
@login_required
def update_payments():
   payments = {}
   # PROCESS pre-populated data
   if MEMBERDATA == "":
	  payments['invalid'] = True
	  payments['membercount'] = 0 
   return render_template('show_payments.html',payments=payments,paysystem=paysystem)




   
if __name__ == '__main__':
    app.run()


