# vim:shiftwidth=2


from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago
from authlibs.accesslib import addQuickAccessQuery
from notices import sendnotices
from sqlalchemy.sql.expression import label

blueprint = Blueprint("prostore", __name__, template_folder='templates', static_folder="static",url_prefix="/prostore")


def log_bin_event(bin,event,commit=0):
	f=[]
	if bin.location_id:
		l = ProLocation.query.filter(ProLocation.id == bin.location_id).one_or_none()
		if l:
			f.append("Loc:%s" % l.location)
	if bin.name:
		f.append("Bin:%s" % bin.name)
	f.append("%s" % ProBin.BinStatuses[int(bin.status)])
	message = " ".join(f)
	authutil.log(event,member_id=bin.member_id,message=message,doneby=current_user.id,commit=commit)

@blueprint.route('/bins', methods=['GET','POST'])
@roles_required(['Admin','RATT','ProStore','Useredit'])
@login_required
def bins():
	if 'create_bin' in request.form:
		b= request.form['input_name']
		
		brec = ProBin()
		if 'input_location' in request.form and request.form['input_location'] != "Unspecified":
			l = request.form['input_location']
			# If it's a "single" location - make sure it's not already in use
			loc = ProLocation.query.filter(ProLocation.location == l).one()
			if loc.loctype == ProLocation.LOCATION_TYPE_SINGLE:
				bincnt = ProBin.query.filter(ProBin.location_id == loc.id).count()
				if bincnt != 0:
					flash("Location is already in-use","danger")
					return redirect(url_for("prostore.bins"))
			brec.location_id = loc.id

		if 'member_radio' in request.form:
			m = request.form['member_radio']
			mem = Member.query.filter(Member.member == m).one()
			brec.member_id = mem.id

		if b.strip() != "":
			bin = ProBin.query.filter(ProBin.name == l).one_or_none()
			if bin:
				flash("Bin name already exists","danger")
				return redirect(url_for("prostore.bins"))

		if b.strip() != "": brec.name=b.strip()
		brec.status = request.form['input_status']
		db.session.add(brec)
		log_bin_event(brec,eventtypes.RATTBE_LOGEVENT_PROSTORE_ASSIGNED.id)
		db.session.commit()
		flash("Bin Added","success")
		return redirect(url_for("prostore.bins"))
		
	bins=ProBin.query	
	bins=bins.outerjoin(ProLocation)
	bins=bins.add_column(ProLocation.location)
	bins=bins.outerjoin(Member)
	bins=bins.add_column(Member.member)

	sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("waiverCount")).group_by(Waiver.member_id)
	sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)
	sq = sq.subquery()
	
	bins = bins.add_column(sq.c.waiverCount.label("waiverCount")).outerjoin(sq,(sq.c.member_id == Member.id))
	bins = bins.outerjoin(Subscription,Subscription.member_id == Member.id)

	bins=addQuickAccessQuery(bins)
	bins=ProBin.addBinStatusStr(bins).all()

	locs=db.session.query(ProLocation,func.count(ProBin.id).label("usecount")).outerjoin(ProBin).group_by(ProLocation.id)
	locs=locs.all()
	return render_template('bins.html',bins=bins,bin=None,locations=locs,statuses=enumerate(ProBin.BinStatuses))

@blueprint.route('/bin/<string:id>', methods=['GET','POST'])
@roles_required(['Admin','ProStore'])
@login_required
def bin_edit(id):
	if 'delete_bin' in request.form:
		bin = ProBin.query.filter(ProBin.id == request.form['input_id']).one()
		log_bin_event(bin,eventtypes.RATTBE_LOGEVENT_PROSTORE_UNASSIGNED.id)
		db.session.delete(bin)
		db.session.commit()
		flash("Bin Deleted","success")	
		return redirect(url_for("prostore.bins"))

	if 'save_bin' in request.form:
		# Save
		print "BIN_EDIT",request.form
		bin = ProBin.query.filter(ProBin.id == request.form['input_id']).one()
		if 'member_radio' in request.form:
			bin.member_id=Member.query.filter(Member.member == request.form['member_radio']).one().id
		elif request.form['unassign_member_hidden'] == "yes":
			bin.member_id = None
		if request.form['input_name']:
			bin.name = request.form['input_name']
		else:
			bin.name=None
		bin.status = request.form['input_status']
		bin.location_id = request.form['input_location']
		log_bin_event(bin,eventtypes.RATTBE_LOGEVENT_PROSTORE_CHANGED.id)
		db.session.commit()
		flash("Updates Saved","success")	
		return redirect(url_for("prostore.bin_edit",id=request.form['input_id']))
			
	b=ProBin.query.filter(ProBin.id==id)
	b=b.add_columns(ProBin.name,ProBin.status)
	b=b.outerjoin(ProLocation)
	b=b.add_column(ProLocation.location)
	b=b.outerjoin(Member)
	b=b.add_column(Member.member)

	b=b.add_column(func.count(Waiver.id).label("waiverDate"))
	b=b.outerjoin(Waiver,((Waiver.member_id == ProBin.member_id) & (Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)))

	b=b.outerjoin(Subscription,Subscription.member_id == Member.id)
	b=addQuickAccessQuery(b)
	b=ProBin.addBinStatusStr(b)
	print "QUERY",b
	b=b.one()
	print b

	locs=db.session.query(ProLocation,func.count(ProBin.id).label("usecount")).outerjoin(ProBin).group_by(ProLocation.id)
	locs=locs.all()
	return render_template('bin.html',bin=b,locations=locs,statuses=enumerate(ProBin.BinStatuses),comments=comments)

@blueprint.route('/locations', methods=['GET','POST'])
@roles_required(['Admin','ProStore'])
@login_required
def locations():
	if 'delete' in request.values:
		loc = ProLocation.query.filter(ProLocation.location==request.values['delete']).one_or_none()
		if not loc:
			flash("Location not found","warning")
		else:
			flash("Location \"%s\" deleted" % request.values['delete'],"success")
			db.session.delete(loc)
			db.session.commit()
	if 'AddLoc' in request.form and 'addloc_name' in request.form:
		newloc = ProLocation()
		newloc.location=request.form['addloc_name']
		newloc.loctype=request.form['input_loctype']
		db.session.add(newloc)
		db.session.commit()
		flash("Location added","success")
		return redirect(url_for("prostore.locations"))
		
	locs=ProLocation.query.order_by(ProLocation.loctype.desc(),ProLocation.location)
	locs=ProLocation.addLocTypeCol(locs,blankSingle=True).all()
	return render_template('locations.html',locations=locs)

@blueprint.route('/grid', methods=['GET','POST'])
@login_required
def grid():
	bins=ProBin.query	
	bins=bins.outerjoin(ProLocation)
	bins=bins.add_column(ProLocation.location)
	bins=bins.outerjoin(Member)
	bins=bins.add_columns(Member.member,Member.lastname,Member.firstname)
	bins=bins.outerjoin(Waiver,((Waiver.member_id == ProBin.member_id) & (Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)))
	bins=bins.add_column(Waiver.created_date.label("waiverDate"))
	bins = bins.outerjoin(Subscription,Subscription.member_id == Member.id)
	bins=addQuickAccessQuery(bins)
	bins=ProBin.addBinStatusStr(bins).all()
	
	ab={}
	for b in bins:
		if b.location:
			ab[b.location] = {
				'binid':b.ProBin.id,
			}
			if b.ProBin.name:
				ab[b.location]['binname']=b.ProBin.name
			else:
				ab[b.location]['binname']=""
				
			if b.member:
				ab[b.location]['member']=b.member
				ab[b.location]['firstname']=b.firstname
				ab[b.location]['lastname']=b.lastname
			else:
				ab[b.location]['firstname']=""
				ab[b.location]['lastname']=""

			if not b.waiverDate:
				ab[b.location]['style'] = "background-color:#ffffd0"
			if b.ProBin.status > 2:
				ab[b.location]['style'] = "background-color:#ffd49f"
			if b.ProBin.status  == 0:
				ab[b.location]['style'] = "background-color:#a3ff9f"
			if b.active != "Active" and b.active != "Grace Period":
				ab[b.location]['style'] = "background-color:#ffd0d0"
	return render_template('grid.html',bins=ab)


@blueprint.route('/notices', methods=['GET','POST'])
@roles_required(['Admin','RATT','ProStore','Useredit'])
@login_required
def notices():
	err=0
	if 'send_notices' in request.form:
		for x in request.form:
			if x.startswith("notify_send_"):
				bid = x.replace("notify_send_","")
				notices = request.form['notify_notices_'+bid]
				err += sendnotices(bid,notices)
		if err:
			flash("%s errors sending email notices" % err,"danger")
		else:
			flash("Notices sent","success")
		
	bins=ProBin.query.filter(ProBin.member_id != None)
	bins=bins.outerjoin(ProLocation)
	bins=bins.add_column(ProLocation.location)
	bins=bins.outerjoin(Member)
	bins=bins.add_column(Member.member)

	sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("waiverCount")).group_by(Waiver.member_id)
	sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)
	sq = sq.subquery()
	
	bins = bins.add_column(sq.c.waiverCount.label("waiverCount")).outerjoin(sq,(sq.c.member_id == Member.id))
	bins = bins.outerjoin(Subscription,Subscription.member_id == Member.id)
	bins=addQuickAccessQuery(bins)
	bins=ProBin.addBinStatusStr(bins).all()

	result=[]
	for b in bins:
		bb={}
		bb['ProBin'] = b.ProBin
		bb['active'] = b.active
		bb['location'] = b.location
		bb['binstatusstr'] = b.binstatusstr
		bb['member'] = b.member
		bb['waiverCount'] = b.waiverCount

		log =Logs.query.filter(Logs.member_id == b.ProBin.member_id).filter(Logs.event_type == eventtypes.RATTBE_LOGEVENT_PROSTORE_NOTICE_SENT.id)
		log = log.order_by(Logs.time_logged.desc()).first()
		if log:
			bb['lastNoticeWhen'] = log.time_reported
			bb['lastNoticeWhat'] = log.message
		else:
			bb['lastNoticeWhen'] = ""
			bb['lastNoticeWhat'] = ""
		# Which notices are recommented??
		rcmd = []
		if b.waiverCount <1: rcmd.append("NoWaiver")
		if b.active != "Active": rcmd.append("Subscription")

		if b.ProBin.status == ProBin.BINSTATUS_GONE:
			rcmd.append("BinGone")
		elif b.ProBin.status == ProBin.BINSTATUS_GRACE_PERIOD:
			rcmd.append("Grace")
		elif b.ProBin.status == ProBin.BINSTATUS_FORFEITED:
			rcmd.append("Forefeit")
		elif b.ProBin.status == ProBin.BINSTATUS_MOVED:
			rcmd.append("Moved")
		elif b.ProBin.status == ProBin.BINSTATUS_DONATED:
			rcmd.append("Donated")
		
		bb['notice']=" ".join(rcmd)
		result.append(bb)

	
	locs=db.session.query(ProLocation,func.count(ProBin.id).label("usecount")).outerjoin(ProBin).group_by(ProLocation.id)
	locs=locs.all()
	return render_template('notices.html',bins=result,bin=None,locations=locs,statuses=enumerate(ProBin.BinStatuses))

	
	
# v0.8 migration
def migrate(cmd,**kwargs):
	for f in ('Garage','Cleanspace'):
		for x in "ABCDEFGH" if f is 'Garage' else "AB":
			for y in range(1,7 if f is 'Garage' else 5):
				name= "%s-%s-%s" % (f,x,y)
				l = ProLocation()
				l.location = name
				l.loctype = 0
				db.session.add(l)
	db.session.commit()

def register_pages(app):
	app.register_blueprint(blueprint)
