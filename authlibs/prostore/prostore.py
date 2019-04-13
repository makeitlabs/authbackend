# vim:shiftwidth=2


from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago

blueprint = Blueprint("prostore", __name__, template_folder='templates', static_folder="static",url_prefix="/prostore")



@blueprint.route('/bins', methods=['GET','POST'])
@roles_required(['Admin','RATT'])
@login_required
def bins():
	print "FORM",request.form
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
	bins=ProBin.addBinStatusStr(bins).all()
	locs=ProLocation.query.order_by(ProLocation.location).all()
	return render_template('bins.html',bins=bins,bin=None,locations=locs,statuses=enumerate(ProBin.BinStatuses))

@blueprint.route('/locations', methods=['GET','POST'])
@roles_required(['Admin','RATT'])
@login_required
def locations():
	print "FORM",request.form
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
		
	locs=ProLocation.query.order_by(ProLocation.location)
	locs=ProLocation.addLocTypeCol(locs,blankSingle=True).all()
	return render_template('locations.html',locations=locs)

def register_pages(app):
	app.register_blueprint(blueprint)
