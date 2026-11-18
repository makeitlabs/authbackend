### GRID MANAGEMENT

def grids():
	"""(Controller) Display Grids and controls"""
	now=datetime.now()
	grids = []
	for x in Grid.query.all():
		grids.append({'id':x.id,
			'name':x.name,
			'description':x.description,
			'slack_admin_chan':x.slack_admin_chan,
			'stripe_desc':x.stripe_desc,
            'priceval':0 if x.price is None else x.price,
            'price':"" if x.price is None else f"${x.price/100.0:0.2f}",
			'product':x.product,
			})
	resources = Resource.query.all()
	return render_template('grids.html',resources=resources,grids=sorted(grids,key=lambda x:x['name']),editable=True,grid={})

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','RATT','ProStore'])
def grids_create():
    """(Controller) Create a grid from an HTML form POST"""
    r = Grid()
    r.name = (request.form['input_name'])
    if r.name is None or r.name.strip() == "":
        flash("No name specified","danger")
        return redirect(url_for('grids.grids'))
    r.description = (request.form['input_description'])
    r.product = (request.form['input_product'])
    p= request.form['input_pricestr']
    try:
        r.price = float(p)*100
    except:
        r.price = None
    r.stripe_desc = (request.form['input_stripe_desc'])
    r.slack_admin_chan = (request.form['input_slack_admin_chan'])
    rid = int(request.form['input_resource_id'])
    if (rid != -1):
        r.resource_id=rid

    db.session.add(r)
    db.session.commit()
    flash("Created.")
    return redirect(url_for('grids.grids'))

@blueprint.route('/<string:grid>', methods=['GET'])
@login_required
def grids_show(grid):
    """(Controller) Display information about a given grid"""
    r = Grid.query.filter(Grid.id==grid).one_or_none()
    if not r:
        flash("Grid not found")
        return redirect(url_for('grids.grids'))
    readonly=False
    if (not current_user.privs('Finance','ProStore')):
        readonly=True
    r.pricestr = "" if r.price is None else f"{r.price/100.0:0.2f}"
    print ("PURCHASBLE ID",r.resource_id)
    resources = Resource.query.all()
    return render_template('grid_edit.html',resources=resources,grid=r,readonly=readonly)

@blueprint.route('/<string:grid>', methods=['POST'])
@login_required
@roles_required(['Admin','RATT','ProStore'])
def grids_update(grid):
        """(Controller) Update an existing grid from HTML form POST"""
        tid = (grid)
        r = Grid.query.filter(Grid.id==tid).one_or_none()
        if not r:
                    flash("Error: Grid not found")
                    return redirect(url_for('grids.grids'))
        r.name = (request.form['input_name'])
        if r.name is None or r.name.strip() == "":
            flash("No name specified","danger")
            return redirect(url_for('grids.grids'))
        r.description = (request.form['input_description'])
        p= request.form['input_pricestr']
        try:
            r.price = float(p)*100
        except:
            r.price = None
        r.product = (request.form['input_product'])
        r.stripe_desc = (request.form['input_stripe_desc'])
        r.slack_admin_chan = (request.form['input_slack_admin_chan'])
        rid = int(request.form['input_resource_id'])
        print ("SET RID TO ",rid)
        if (rid == -1):
            r.resource_id=None
        else:
            r.resource_id=rid
        db.session.commit()
        flash("Grid updated")
        return redirect(url_for('grids.grids'))

@blueprint.route('/<string:grid>/delete',methods=['GET','POST'])
@roles_required(['Admin','RATT','ProStore'])
def grid_delete(grid):
    """(Controller) Delete a grid. Shocking."""
    r = Grid.query.filter(Grid.id == grid).one()
    db.session.delete(r)
    db.session.commit()
    flash("Grid deleted.")
    return redirect(url_for('grids.grids'))


## END GRID MANAGEMENT
