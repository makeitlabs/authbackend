# vim:shiftwidth=2


from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago
import stripe
from authlibs.slackutils import send_slack_message

blueprint = Blueprint("purchasables", __name__, template_folder='templates', static_folder="static",url_prefix="/purchasables")



@blueprint.route('/', methods=['GET'])
@login_required
def purchasables():
	"""(Controller) Display Purchasables and controls"""
	now=datetime.now()
	purchasables = []
	for x in Purchasable.query.all():
		purchasables.append({'id':x.id,
			'name':x.name,
			'description':x.description,
			'slack_admin_chan':x.slack_admin_chan,
			'stripe_desc':x.stripe_desc,
            'priceval':0 if x.price is None else x.price,
            'price':"" if x.price is None else f"${x.price/100.0:0.2f}",
			'product':x.product,
			'resource_id':x.resource_id,
			})
	resources = Resource.query.all()
	return render_template('purchasables.html',resources=resources,purchasables=sorted(purchasables,key=lambda x:x['name']),editable=True,purchasable={},)

@blueprint.route('/create', methods=['POST'])
@login_required
@roles_required(['Admin','Finance'])
def purchasables_create():
    """(Controller) Create a purchasable from an HTML form POST"""
    r = Purchasable()
    r.name = (request.form['input_name'])
    if r.name is None or r.name.strip() == "":
        flash("No name specified","danger")
        return redirect(url_for('purchasables.purchasables'))
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
    return redirect(url_for('purchasables.purchasables'))

@blueprint.route('/show/<string:purchasable>', methods=['GET'])
@login_required
def purchasables_show(purchasable):
    """(Controller) Display information about a given purchasable"""
    r = Purchasable.query.filter(Purchasable.id==purchasable).one_or_none()
    if not r:
        flash("Purchasable not found")
        return redirect(url_for('purchasables.purchasables'))
    readonly=False
    if (not current_user.privs('Finance')):
        readonly=True
    r.pricestr = "" if r.price is None else f"{r.price/100.0:0.2f}"
    print ("PURCHASBLE ID",r.resource_id)
    resources = Resource.query.all()
    return render_template('purchasable_edit.html',resources=resources,purchasable=r,readonly=readonly)

@blueprint.route('/show/<string:purchasable>', methods=['POST'])
@login_required
@roles_required(['Admin','Finance'])
def purchasables_update(purchasable):
        """(Controller) Update an existing purchasable from HTML form POST"""
        tid = (purchasable)
        r = Purchasable.query.filter(Purchasable.id==tid).one_or_none()
        if not r:
                    flash("Error: Purchasable not found")
                    return redirect(url_for('purchasables.purchasables'))
        r.name = (request.form['input_name'])
        if r.name is None or r.name.strip() == "":
            flash("No name specified","danger")
            return redirect(url_for('purchasables.purchasables'))
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
        flash("Purchasable updated")
        return redirect(url_for('purchasables.purchasables'))

@blueprint.route('/delete/<string:purchasable>',methods=['GET','POST'])
@roles_required(['Admin','Finance'])
def purchasable_delete(purchasable):
    """(Controller) Delete a purchasable. Shocking."""
    r = Purchasable.query.filter(Purchasable.id == purchasable).one()
    db.session.delete(r)
    db.session.commit()
    flash("Purchasable deleted.")
    return redirect(url_for('purchasables.purchasables'))

@blueprint.route('/quick/<int:purchasable>',defaults={'ident':"",'cost': 0}, methods=['GET'])
@blueprint.route('/quick/<int:purchasable>/<int:cost>/<string:ident>', methods=['GET'])
@blueprint.route('/quick/<int:purchasable>/<int:cost>',defaults={'ident': ""}, methods=['GET'])
@login_required
def quick(purchasable,cost,ident):

    sub = Subscription.query.filter(Subscription.member_id == current_user.id).one_or_none()
    if sub is None:
        flash("No subscription found","danger")
        return redirect(url_for('purchasables.purchasables'))

    cid = sub.customerid
    #print("Customer ID is",cid)
    r = Purchasable.query.filter(Purchasable.id == purchasable).one()
    #print ("Product code is ",r.product)
    if r.product is None or r.product.strip() =="":
        flash("Error: Product code is undefined","danger")
        return redirect(url_for('purchasables.purchasables'))
    if cost == 0:
        cost = r.price
    if cost is None:
        cost = 0
    cs = f"{cost/100:0.2f}"
    if ident == "":
        ident = r.description
    if (ident != ""):
        ident = "("+ident+")"
    return render_template('quick.html',purchasable=r,cost=cost,ident=ident,chargeStr=cs)

@blueprint.route('/purchase', methods=['POST'])
@login_required
def purchasable_purchase():

    sub = Subscription.query.filter(Subscription.member_id == current_user.id).one_or_none()
    if sub is None:
        flash("No subscription found","danger")
        return redirect(url_for('purchasables.purchasables'))
    ps = request.form['pricestr'].replace('$','')
    cents = int(float(ps)*100.0)

    cid = sub.customerid
    #print("Customer ID is",cid)
    rid = (request.form['purchase_item_id'])
    r = Purchasable.query.filter(Purchasable.id == rid).one()
    #print ("Product code is ",r.product)
    if r.product is None or r.product.strip() =="":
        flash("Error: Product code is undefined","danger")
        return redirect(url_for('purchasables.purchasables'))
    maxpurchase = float(current_app.config['globalConfig'].Config.get('Stripe','MaxPurchasable'))
    if (cents <= 0):
        flash("Invalid price specified","danger")
        return redirect(url_for('purchasables.purchasables'))
    if (cents > maxpurchase):
        flash("Price excedes maximum allowable")
        return redirect(url_for('purchasables.purchasables'))


    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','VendingToken')
    stripedesc = r.stripe_desc
    commentstr=""
    if 'comment' in request.form and request.form['comment'].strip() != "": 
        commentstr=request.form['comment'].strip()
        stripedesc= f"{stripedesc} ({commentstr})"
        commentstr=f" ({request.form['comment'].strip()})"
    try:
        price = stripe.Price.create(
          unit_amount=cents,
          currency='usd',
          product=r.product)

        invoice = stripe.Invoice.create(
        customer=cid,
        pending_invoice_items_behavior="exclude",
        description=stripedesc
        #collection_method="charge_automatically",
        )

        invoiceItem = stripe.InvoiceItem.create(customer=cid, price=price, description=stripedesc, invoice=invoice.id)

        finalize=stripe.Invoice.finalize_invoice(invoice)
        if (finalize['status'] == 'paid'):
            pass
        elif (finalize['status'] == 'open'):
            pay = stripe.Invoice.pay(invoice)
            if (pay['status'] != 'paid'):
              #result = {'error':'success','description':"Payment Declined"}
              flash("Payment was Declined","danger")
              logger.warning("Stripe Payment error for {0} status is {1} productId {2} customerId {3}".format(current_user.member,pay['status'],r.product,cid))
              return redirect(url_for('purchasables.purchasables'))
        else:
            #result = {'error':'success','description':"Stripe Error"}
            flash(f"Charge error: {finalize['status']}","danger")
            logger.warning("Stripe Finalize error for {0} status is {1} productId {2} customerId {3}".format(current_user.member,pay['status'],r.product,cid))
            return redirect(url_for('purchasables.purchasables'))
    except BaseException as e:
      flash(f"Stripe error: {e}","danger")
      logger.warning("Stripe Payment error for {0} productId {1} customerId {2}: {3}".format(current_user.member,r.product,cid,e))
      return redirect(url_for('purchasables.purchasables'))

    flash("Payment succeed","success")
    try:
        if (r.slack_admin_chan is not None) and (r.slack_admin_chan.strip() != ""):
            send_slack_message(r.slack_admin_chan,f":moneybag: {current_user.firstname} {current_user.lastname} purchased {r.name} for ${request.form['pricestr']}{commentstr}")
    except:
        pass
    logmsg = f"Purchased {r.name} for ${request.form['pricestr']}{commentstr}"
    authutil.log(eventtypes.RATTBE_LOGEVENT_PURCHASABLE_PURCHASE.id,resource_id=r.resource_id,member_id=current_user.id,message=logmsg,commit=0)

    # If this purchasable is inventory-tracked, also deduct from inventory
    latest_inv = InventoryLog.query.filter(
        InventoryLog.purchasable_id == r.id
    ).order_by(InventoryLog.id.desc()).first()
    if latest_inv is not None:
        old_qty = latest_inv.new_quantity if latest_inv.new_quantity is not None else 0
        new_qty = old_qty - 1
        il = InventoryLog(
            purchasable_id=r.id,
            resource_id=r.resource_id,
            member_id=current_user.id,
            operation='purchase',
            quantity=1,
            unit_price=cents,
            total_price=cents,
            old_quantity=old_qty,
            new_quantity=new_qty,
            comment=f"Quick purchase{commentstr}" if commentstr else "Quick purchase"
        )
        db.session.add(il)

    db.session.commit()
    return redirect(url_for('purchasables.purchasables'))

@blueprint.route('/<string:purchasable>/list', methods=['GET'])
@login_required
def purchasable_showusers(purchasable):
    """(Controller) Display users who are authorized to use this purchasable"""
    tid = (purchasable)
    authusers = db.session.query(AccessByMember.id,AccessByMember.member_id,Member.member)
    authusers = authusers.outerjoin(Member,AccessByMember.member_id == Member.id)
    authusers = authusers.filter(AccessByMember.purchasable_id == db.session.query(Purchasable.id).filter(Purchasable.name == rid))
    authusers = authusers.all()
    return render_template('purchasable_users.html',purchasable=rid,users=authusers)

#TODO: Create safestring converter to replace string; converter?
@blueprint.route('log//<string:purchasable>', methods=['GET','POST'])
@roles_required(['Admin','Finance'])
def logging(purchasable):
     """Endpoint for a purchasable to log via API"""
     # TODO - verify purchasables against global list
     if request.method == 'POST':
        # YYYY-MM-DD HH:MM:SS
        # TODO: Filter this for safety
        logdatetime = request.form['logdatetime']
        level = safestr(request.form['level'])
        # 'system' for purchasable system, rfid for access messages
        userid = safestr(request.form['userid'])
        msg = safestr(request.form['msg'])
        sqlstr = "INSERT into logs (logdatetime,purchasable,level,userid,msg) VALUES ('%s','%s','%s','%s','%s')" % (logdatetime,purchasable,level,userid,msg)
        execute_db(sqlstr)
        get_db().commit()
        return render_template('logged.html')
     else:
        if current_user.is_authenticated:
                r = safestr(purchasable)
                sqlstr = "SELECT logdatetime,purchasable,level,userid,msg from logs where purchasable = '%s'" % r
                entries = query_db(sqlstr)
                return render_template('purchasable_log.html',entries=entries)
        else:
                abort(401)

def register_pages(app):
	app.register_blueprint(blueprint)
