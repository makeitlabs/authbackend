# vim:shiftwidth=2


from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago
from authlibs.accesslib import addQuickAccessQuery

blueprint = Blueprint("prostore", __name__, template_folder='templates', static_folder="static",url_prefix="/prostore")



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
		db.session.commit()
		flash("Bin Added","success")
		return redirect(url_for("prostore.bins"))
		
	bins=ProBin.query	
	bins=bins.outerjoin(ProLocation)
	bins=bins.add_column(ProLocation.location)
	bins=bins.outerjoin(Member)
	bins=bins.add_column(Member.member)
	bins=bins.outerjoin(Waiver,((Waiver.member_id == ProBin.member_id) & (Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)))
	bins=bins.add_column(Waiver.created_date.label("waiverDate"))
	bins = bins.outerjoin(Subscription,Subscription.member_id == Member.id)
	bins=addQuickAccessQuery(bins)
	bins=ProBin.addBinStatusStr(bins).all()

	locs=db.session.query(ProLocation,func.count(ProBin.id).label("usecount")).outerjoin(ProBin).group_by(ProLocation.id)
	locs=locs.all()
	return render_template('bins.html',bins=bins,bin=None,locations=locs,statuses=enumerate(ProBin.BinStatuses))

@blueprint.route('/bin/<string:id>', methods=['GET','POST'])
@roles_required(['Admin','RATT','ProStore'])
@login_required
def bin_edit(id):
	if 'save_bin' in request.form:
		# Save
		print "BIN_EDIT",request.form
	b=ProBin.query.filter(ProBin.id==id)
	b=b.add_columns(ProBin.name,ProBin.status)
	b=b.outerjoin(ProLocation)
	b=b.add_column(ProLocation.location)
	b=b.outerjoin(Member)
	b=b.add_column(Member.member)
	b=b.outerjoin(Waiver,((Waiver.member_id == ProBin.member_id) & (Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)))
	b=b.add_column(Waiver.created_date.label("waiverDate"))
	b = b.outerjoin(Subscription,Subscription.member_id == Member.id)
	b=addQuickAccessQuery(b)
	b=ProBin.addBinStatusStr(b).one()

	locs=db.session.query(ProLocation,func.count(ProBin.id).label("usecount")).outerjoin(ProBin).group_by(ProLocation.id)
	locs=locs.all()
	return render_template('bin.html',bin=b,locations=locs,statuses=enumerate(ProBin.BinStatuses))

@blueprint.route('/locations', methods=['GET','POST'])
@roles_required(['Admin','RATT','ProStore'])
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
@roles_required(['Admin','RATT','ProStore'])
@login_required
def grid():
	bins=ProBin.query	
	bins=bins.outerjoin(ProLocation)
	bins=bins.add_column(ProLocation.location)
	bins=bins.outerjoin(Member)
	bins=bins.add_column(Member.member)
	bins=bins.outerjoin(Waiver,((Waiver.member_id == ProBin.member_id) & (Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)))
	bins=bins.add_column(Waiver.created_date.label("waiverDate"))
	bins = bins.outerjoin(Subscription,Subscription.member_id == Member.id)
	bins=addQuickAccessQuery(bins)
	bins=ProBin.addBinStatusStr(bins).all()
	
	ab={}
	for b in bins:
		if b.location and b.member:
			ab[b.location] = {
				'member':b.member,
				'binid':b.ProBin.id
			}
			if not b.waiverDate:
				ab[b.location]['style'] = "background-color:#ffffd0"
			if b.ProBin.status > 2:
				ab[b.location]['style'] = "background-color:#ffd49f"
			if b.ProBin.status  == 0:
				ab[b.location]['style'] = "background-color:#a3ff9f"
			if b.active != "Active" and b.active != "Grace Period":
				ab[b.location]['style'] = "background-color:#ffd0d0"
	return render_template('grid.html',bins=ab)
	
	
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
