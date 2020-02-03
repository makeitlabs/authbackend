# vim:shiftwidth=2

from ..templateCommon import  *

from authlibs import smartwaiver 
waiversystem = {}

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("waivers", __name__, template_folder='templates', static_folder="static",url_prefix="/waivers")

# ------------------------------------------------------------
# Waiver controllers
# ------------------------------------------------------------

@blueprint.route('/', methods=['GET'])
@roles_required(['Admin','Finance','Useredit'])
@login_required
def waivers():
		waivers = Waiver.query.order_by(Waiver.id.desc())
		waivers = waivers.add_column(Member.member).outerjoin(Member,Member.id == Waiver.member_id)
		res=[]
		for (waiver,member) in waivers.all():
			if member is None: member=""
			res.append({'waiver':waiver,'member':member,'code':waiver.waivertype,'type':waiver.shortFromCode(waiver.waivertype)})
		types=[{'code':-1,'short':"All Waivers"}]
		types += Waiver.waiverTypes
		return render_template('waivers.html',waivers=res,types=types)

@blueprint.route('/', methods=['POST'])
@roles_required(['Admin','Finance','Useredit'])
@login_required
def post_waivers():
		if 'Unlink' in request.form and request.form['Unlink']=='Unlink':
			wid = request.form['unlink_waiver_id']
			w = Waiver.query.filter(Waiver.id == wid).one()
			m = Member.query.filter(Member.id == w.member_id).one_or_none()
			w.member_id = None
			if m:
				if (w.waivertype == Waiver.WAIVER_TYPE_MEMBER):
					authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_ACCESS_DISABLED.id,message="Waiver was unlinked",member_id=m.id,doneby=current_user.id,commit=0)
					m.access_enabled=0 # BKG TODO FIX in v0.8 ONLY if "member" waiver
					flash("User access disabled because of no waiver from Waiver","warning")
			authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_WAIVER_UNLINKED.id,member_id=m.id,doneby=current_user.id,commit=0)
			db.session.commit()
			flash("Unlinked from Waiver","warning")
		return redirect(url_for("waivers.waivers"))

@blueprint.route('/update', methods=['GET'])
@roles_required(['Admin','Finance','Useredit'])
@login_required
def waivers_update():
		"""(Controller) Update list of waivers in the database. Can take a while."""
		updated = addNewWaivers()
		flash("Waivers added: %s" % updated)
		connect_waivers()
		return redirect(url_for('waivers.waivers'))

###
### Utilities
###


def _addWaivers(waiver_list):
    """Add list-based Waiver data into the waiver table in the database"""
    for w in waiver_list:
      n = Waiver()
      n.waiver_id= w['waiver_id']
      n.email=w['email']
      n.firstname=w['firstname']
      n.lastname=w['lastname']
      n.waivertype = Waiver.codeFromWaiverTitle(w['title'])
      n.created_date=authutil.parse_datetime(w['created_date'])
      cnt = db.session.query(Waiver).filter(Waiver.waiver_id == w['waiver_id']).count()
      #print "WID {0} count {1}".format(w['waiver_id'],cnt)
      if cnt==0:
        logger.debug("Add new waiver {0} {1} {2} {3} {4} {5}".format(n.waiver_id,n.email,n.lastname,n.firstname,n.waivertype,n.created_date))
        db.session.add(n)
    logger.debug("Skipping existing waiver {0} {1} {2} {3} {4} {5}".format(n.waiver_id,n.email,n.lastname,n.firstname,n.waivertype,n.created_date))
    db.session.commit()
    logger.debug("Waiver updates committed")
    return len(waiver_list)

def addNewWaivers():
	"""Check the DB to get the most recent waiver, add any new ones, return count added"""
	logger.debug ("Updating waivers...")
	waiversystem = {}
	waiversystem['Apikey'] = current_app.config['globalConfig'].Config.get('Smartwaiver','Apikey')
	(last_waiverid,last_date) = smartwaiver.getLastWaiver()
	waiver_dict = {'api_key': waiversystem['Apikey'],'waiver_id': last_waiverid,'last_date':last_date}
	waivers = smartwaiver.getWaivers(waiver_dict)
	logger.debug("Checking {0} new waivers".format(len(waivers)))
	return _addWaivers(waivers)
	logger.debug ("Done.")

def cli_waivers(cmd,**kwargs):
	addNewWaivers()

# This should ONLY be required for v0.7->v0.8 Migrations
def cli_fix_waiver_types(cmd,**kwargs):
  logger.debug ("Updating waivers...")
  waiversystem = {}
  waiversystem['Apikey'] = current_app.config['globalConfig'].Config.get('Smartwaiver','Apikey')
  waiver_dict = {'api_key': waiversystem['Apikey'],'waiver_id': None}
  waivers = smartwaiver.getWaivers(waiver_dict)
  logger.debug ("Collected - updating.")
  good=0
  for w in waivers:
    n = Waiver.query.filter(Waiver.waiver_id == w['waiver_id']).all()
    for x in n:
      x.waivertype = Waiver.codeFromWaiverTitle(w['title'])
      for m in  Member.query.filter(Member.email.ilike(x.email)).all():
          x.member_id = m.id
      good+=1
  logger.debug("Updated %s" % good)
  db.session.commit() 

def register_pages(app):
  app.register_blueprint(blueprint)

def removed_from_register_pages():
  waiversystem = {}
  waiversystem['Apikey'] = app.config['globalConfig'].Config.get('Smartwaiver','Apikey')
  logger.debug ("Getting ALL waivers...")
  waiversystem = {}
  waiversystem['Apikey'] = current_app.config['globalConfig'].Config.get('Smartwaiver','Apikey')
  last_waiverid = smartwaiver.getLastWaiverId()
  waiver_dict = {'api_key': waiversystem['Apikey'],'waiver_id': last_waiverid}
  waivers = smartwaiver.getWaivers(waiver_dict)
  logger.debug ("Done.")

def connect_waivers():
	logger.debug("CONNECING WAIVERS")
	for w in Waiver.query.filter(Waiver.member_id == None).all():
		s =  "Unattached %s %s %s " % (w.email,w.firstname,w.lastname)
		m = Member.query.filter(or_((Member.alt_email.ilike(w.email)),(Member.email.ilike(w.email))))
		m = m.filter(Member.firstname.ilike(w.firstname))
		m = m.filter(Member.lastname.ilike(w.lastname))
		m = m.all()
		if len(m)==1:
			w.member_id = m[0].id
			s += " accept waiver for member %s" % m[0].member
			if (w.waivertype == Waiver.WAIVER_TYPE_MEMBER):
				if  (m[0].access_reason is None or m[0].access_reason == ""):
					m[0].access_enabled=1;
					authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_WAIVER_ACCEPTED.id,member_id=m[0].id,commit=0)
				else:
					authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_ACCESS_DISABLED.id,message="Waiver found, but access otherwise denied",member_id=m[0].id,commit=0)
		#else:
		#	print s+" ?? len "+str(len(m))
	db.session.commit()

def cli_waivers_connect(*cmd,**kvargs):
	connect_waivers()
