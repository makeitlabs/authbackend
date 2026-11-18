# vim:shiftwidth=2:noexpandtab

from ..templateCommon import  *

import math
from authlibs import accesslib
from authlibs import ago
from authlibs.comments import comments
from authlibs.slackutils import send_slack_message
import datetime
from . import graph
from ..google_admin import genericEmailSender
from functools import cmp_to_key
import stripe

blueprint = Blueprint("resources", __name__, template_folder='templates', static_folder="static",url_prefix="/resources")
# ----------------------------------------------------
# Resource management (not including member access)
# Routes:
#  /resources - View
#  /resources/<name> - Details for specific resource
#  /resources/<name>/access - Show access for resource
# ------------------------------------------------------

@blueprint.route('/', methods=['GET'])
@login_required
def resources():
	 """(Controller) Display Resources and controls"""
	 resources = _get_resources()
	 access = {}
	 resources = sorted(resources,key=lambda x: x['name'])
	 return render_template('resources.html',resources=resources,access=access,editable=True)

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def resource_create():
	"""(Controller) Create a resource from an HTML form POST"""
	r = Resource()
	r.name = (request.form['input_name']).strip()
	r.short = (request.form['input_short']).strip()
	r.description = (request.form['input_description']).strip()
	if r.name=="" or r.short=="" or r.description=="":
	  flash("Name, Short and Description are manditory","warning")
	  return redirect(url_for('resources.resources'))
	r.owneremail = (request.form['input_owneremail']).strip()
	r.slack_chan = (request.form['input_slack_chan']).strip()
	r.prodcode = (request.form['input_prodcode']).strip()
	try: 
	    r.price = int(request.form['input_price'])
	except:
	    pass
	try: 
	    r.price_pro = int(request.form['input_price_pro'])
	except:
	    pass
	try: 
	    r.free_min = int(request.form['input_free_min'])
	except:
	    pass
	try: 
	    r.free_min_pro = int(request.form['input_free_min_pro'])
	except:
	    pass
	r.slack_admin_chan = (request.form['input_slack_admin_chan']).strip()
	r.event_mqtt_topic = (request.form['input_event_mqtt_topic']).strip()
	r.info_url = (request.form['input_info_url']).strip()
	r.info_text = (request.form['input_info_text']).strip()
	r.slack_info_text = (request.form['input_slack_info_text']).strip()
	r.slack_info_text = (request.form['input_slack_info_text']).strip()
	if request.form['input_age_restrict']:
		ar = 0
		try:
			ar = int(request.form['input_age_restrict'])
		except:
			pass
		if ar == 0:
			flash("Age restriction should be empty, or greater than zero","warning")
	else:
		r.age_restrict = None
	db.session.add(r)
	db.session.commit()
	authutil.kick_backend()
	flash("Created.")
	return redirect(url_for('resources.resources'))

@blueprint.route('/<string:resource>', methods=['GET'])
@login_required
def resource_show(resource):
	"""(Controller) Display information about a given resource"""
	r = Resource.query.filter(Resource.name==resource).one_or_none()
	tools = Tool.query.filter(Tool.resource_id==r.id).all()
	if not r:
		flash("Resource not found")
		return redirect(url_for('resources.resources'))

	readonly=True
	if accesslib.user_privs_on_resource(member=current_user,resource=r) >= AccessByMember.LEVEL_ARM:
		readonly=False

	cc=comments.get_comments(resource_id=r.id)

	maint= MaintSched.query.filter(MaintSched.resource_id==r.id).all()
	train=[]
	for t in Training.query.filter(Training.resource_id==r.id).all():
		v={'id':t.id}
		if t.endorsements is None or t.endorsements.strip() == "":
			v['grants'] = "(General Access)"
		else:
			v['grants'] = t.endorsements + " Endorsement"

		if t.name is None or t.name.strip()=="":
			v['name'] = r.short.title()+" "+v['grants']
		else:
			v['name']= t.name

		if t.required is None:
			v['requires']="(None)"
		else:
			v['requires']= Resource.query.filter(Resource.id == t.required).one().short.title()
			if t.required_endorsements is not None and t.required_endorsements.strip()!="":
				v['requires'] += " " + t.required_endorsements + " endorsement"

		train.append(v)
		
			

	resources = Resource.query.all()
	resources = sorted(resources,key=lambda x: x.name)
	
	from authlibs.db_models import ResourceNotice
	notices = ResourceNotice.query.filter((ResourceNotice.resource_id == r.id) & (ResourceNotice.active == True)).all()

	return render_template('resource_edit.html',rec=r,resources=resources,readonly=readonly,tools=tools,comments=cc,maint=maint,train=train, notices=notices)

@blueprint.route('/<string:resource>/usage', methods=['GET'])
@login_required
def resource_usage(resource):
	"""(Controller) Display information about a given resource"""
	r = Resource.query.filter(Resource.name==resource).one_or_none()
	tools = Tool.query.filter(Tool.resource_id==r.id).all()
	if not r:
		flash("Resource not found")
		return redirect(url_for('resources.resources'))

	readonly=True
	if accesslib.user_privs_on_resource(member=current_user,resource=r) >= AccessByMember.LEVEL_ARM:
		readonly=False

	cc=comments.get_comments(resource_id=r.id)
	return render_template('resource_usage.html',rec=r,readonly=readonly,tools=tools,comments=cc)

def generate_report(fields,records):
	for r in records:
			yield ",".join(["\"%s\"" % r[f['name']] for f in fields]) + "\n"

def sec_to_hms(sec):
	h=0
	m=0
	s=0
	h = math.floor(sec/3600)
	m = math.floor(math.fmod(sec,3600)/60)
	s = math.fmod(sec,60)
	return "{0:2.0f}:{1:02.0f}:{2:02.0f}".format(h,m,s)
	
@blueprint.route('/<string:resource>/usagereports', methods=['GET'])
@login_required
def resource_usage_reports(resource):
	"""(Controller) Display information about a given resource"""

	r = Resource.query.filter(Resource.name==resource).one_or_none()
	tools = Tool.query.filter(Tool.resource_id==r.id).all()
	if not r:
		flash("Resource not found")
		return redirect(url_for('resources.resources'))

	readonly=True
	if accesslib.user_privs_on_resource(member=current_user,resource=r) >= AccessByMember.LEVEL_ARM:
		readonly=False

	q = UsageLog.query.filter(UsageLog.resource_id==r.id)
	if 'input_date_start' in request.values and request.values['input_date_start'] != "":
			dt = datetime.datetime.strptime(request.values['input_date_start'],"%m/%d/%Y")
			q = q.filter(UsageLog.time_logged >= dt)
	if 'input_date_end' in request.values and request.values['input_date_end'] != "":
			dt = datetime.datetime.strptime(request.values['input_date_end'],"%m/%d/%Y")+datetime.timedelta(days=1)
			q = q.filter(UsageLog.time_logged < dt)

	q = q.add_column(func.sum(UsageLog.enabledSecs).label('enabled'))
	q = q.add_column(func.sum(UsageLog.activeSecs).label('active'))
	q = q.add_column(func.sum(UsageLog.idleSecs).label('idle'))

	fields=[]
	if 'by_user' in request.values:
		q = q.group_by(UsageLog.member_id).add_column(UsageLog.member_id.label("member_id"))
		fields.append({'name':"member"})
	if 'by_tool' in request.values:
		q = q.group_by(UsageLog.tool_id).add_column(UsageLog.tool_id.label("tool_id"))
		fields.append({'name':"tool"})
	if 'by_day' in request.values:
		q = q.group_by(func.date(UsageLog.time_logged)).add_column(func.date(UsageLog.time_logged).label("date"))
		q = q.order_by(func.date(UsageLog.time_logged))
		fields.append({'name':"date"})
	fields +=[{'name':'enabled','type':'num'},{'name':'active','type':'num'},{'name':'idle','type':'num'}]

	d = q.all()
	toolcache={}
	usercache={}
	records=[]
	for r in d:
		if 'format' in request.values and request.values['format']=='csv':
			rec={'enabled':r.enabled,'active':r.active,'idle':r.idle}
		else:
			rec={'enabled':sec_to_hms(r.enabled),'active':sec_to_hms(r.active),'idle':sec_to_hms(r.idle),
					'enabled_secs':int(r.enabled),'active_secs':int(r.active),'idle_secs':int(r.idle)}
		if 'by_user' in request.values:
			if r.member_id not in usercache:
				mm = Member.query.filter(Member.id==r.member_id).one_or_none()
				if mm:
					usercache[r.member_id] = mm.member
				else:
					usercache[r.member_id] = "Member #"+str(r.member_id)
			rec['member'] = usercache[r.member_id]
		if 'by_tool' in request.values:
			if r.tool_id not in toolcache:
				mm = Tool.query.filter(Tool.id==r.tool_id).one_or_none()
				if mm:
					toolcache[r.tool_id] = mm.name
				else:
					toolcache[r.tool_id] = "Tool #"+str(r.tool_id)
			rec['tool'] = toolcache[r.tool_id]
		if 'by_day' in request.values:
			rec['date'] = r.date
		records.append(rec)
		
	meta={}
	meta['csvurl']=request.url+"&format=csv"

	if 'format' in request.values and request.values['format']=='csv':
		resp=Response(generate_report(fields,records),mimetype='text/csv')
		resp.headers['Content-Disposition']='attachment'
		resp.headers['filename']='log.csv'
		return resp

	return render_template('resource_usage_reports.html',rec=r,readonly=readonly,tools=tools,records=records,fields=fields,meta=meta)

@blueprint.route('/<string:resource>/addmaint', methods=['POST'])
@login_required
def add_maint(resource):
	#print ("RESOURCE",resource)
	r = Resource.query.filter(Resource.name==resource).one_or_none()
	if not r:
		flash("Error: Resource not found")
		return redirect(url_for('resources.resources'))
	m = MaintSched()
	m.resource_id = r.id
	if (request.form['input_maint_time_span'].strip() != ""):
		try:
			v=  int(request.form['input_maint_time_span'].strip())
		except:
			v=0
		if (v <= 0):
			flash("Error: Invalid time value entered")
			return redirect(url_for('resources.resources'))
			
		m.realtime_span = v
		m.realtime_unit = request.form['input_maint_time_interval']
		
	if (request.form['input_maint_runtime_span'].strip() != ""):
		try:
			v=  int(request.form['input_maint_runtime_span'].strip())
		except:
			v=0
		if (v <= 0):
			flash("Error: Invalid time value entered")
			return redirect(url_for('resources.resources'))
		m.machinetime_span = v
		m.machinetime_unit = request.form['input_maint_runtime_interval']
	
	m.name = request.form['input_maint_name'].strip()
	if m.name == "":
			flash("Error: No \"name\" specified")
			return redirect(url_for('resources.resources'))
	m.name = m.name.replace(" ","-")
	m.name = m.name.replace("_","-")
	m.desc = request.form['input_maint_desc'].strip()
	db.session.add(m)
	flash("Added","success")
	db.session.commit()
	return redirect(url_for('resources.resource_show',resource=r.name))

@blueprint.route('/<string:resource>', methods=['POST'])
@login_required
def resource_update(resource):
		"""(Controller) Update an existing resource from HTML form POST"""
		rname = (resource)
		r = Resource.query.filter(Resource.id==resource).one_or_none()
		if not r:
			flash("Error: Resource not found")
			return redirect(url_for('resources.resources'))
		if accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
			flash("Error: Permission denied")
			return redirect(url_for('resources.resources'))

		r.name = (request.form['input_name']).strip()
		r.short = (request.form['input_short']).strip()
		r.description = (request.form['input_description']).strip()
		if r.name=="" or r.short=="" or r.description=="":
		  flash("Name, Short and Description are manditory","warning")
		  return redirect(url_for('resources.resources'))
		r.owneremail = (request.form['input_owneremail']).strip()
		r.slack_chan = (request.form['input_slack_chan']).strip()
		r.prodcode = (request.form['input_prodcode']).strip()
		try: 
			r.price = int(request.form['input_price'])
		except:
			pass
		try: 
			r.price_pro = int(request.form['input_price_pro'])
		except:
			pass
		try: 
			r.free_min = int(request.form['input_free_min'])
		except:
			pass
		try: 
			r.free_min_pro = int(request.form['input_free_min_pro'])
		except:
			pass
		r.slack_admin_chan = (request.form['input_slack_admin_chan']).strip()
		r.event_mqtt_topic = (request.form['input_event_mqtt_topic']).strip()
		r.info_url = (request.form['input_info_url']).strip()
		r.info_text = (request.form['input_info_text']).strip()
		r.slack_info_text = (request.form['input_slack_info_text']).strip()
		r.permissions = (request.form['input_permissions']).replace("_","-").strip()
		if request.form['input_age_restrict']:
			ar = 0
			try:
				ar = int(request.form['input_age_restrict'])
				r.age_restrict = ar
			except:
				pass
			if ar <= 0:
				flash("Age restriction should be empty, or greater than zero","warning")
		else:
			r.age_restrict = None
		db.session.commit()
		authutil.kick_backend()
		flash("Resource updated")
		return redirect(url_for('resources.resources'))

@blueprint.route('/<string:resource>/delete', methods=['POST'])
@roles_required(['Admin','RATT'])
def resource_delete(resource):
    """(Controller) Delete a resource. Shocking."""
    r = Resource.query.filter(Resource.id == resource).one()
    db.session.delete(r)
    db.session.commit()
    flash("Resource deleted.")
    return redirect(url_for('resources.resources'))

def showuser_sort(a,b):
  if (a['sortlevel'] < b['sortlevel']): return 1
  if (a['sortlevel'] > b['sortlevel']): return -1

  if (a['sorttime'] and not b['sorttime']): return -1
  if (not a['sorttime'] and b['sorttime']): return 1
  if (not a['sorttime'] and not b['sorttime']): return 0
  return int((b['sorttime'] - a['sorttime']).total_seconds())


	
@blueprint.route('/<string:resource>/list', methods=['GET'])
def resource_showusers(resource):
    debug=[]
    """(Controller) Display users who are authorized to use this resource"""
    rid = (resource)
    res_id = Resource.query.filter(Resource.name == rid).one_or_none()
    if not res_id:
      flash ("Resource not found","warning")
      return redirect(url_for('resources.resources'))

    res_id=res_id.id
    mid_to_lastuse={}

    for u in  UsageLog.query.filter(UsageLog.resource_id == res_id).group_by(UsageLog.member_id).order_by(func.max(UsageLog.time_logged)).all():
      mid_to_lastuse[u.member_id] = u.time_logged

    authusers = db.session.query(AccessByMember.id,AccessByMember.member_id,Member.member,AccessByMember.level,AccessByMember.lockout_reason,AccessByMember.permissions)
    authusers = authusers.join(Member,AccessByMember.member_id == Member.id)
    authusers = authusers.filter(AccessByMember.resource_id == db.session.query(Resource.id).filter(Resource.name == rid))
    authusers = authusers.order_by(AccessByMember.level.desc())
    authusers = authusers.all()
    accrec=[]
    now = datetime.datetime.utcnow()
    for x in authusers:
      level = accessLevelToString(x[3],blanks=[0,-1])
      lu1=""
      lu2=""
      lu3=""
      sorttime = None
      if x[1] in mid_to_lastuse: 
        if mid_to_lastuse[x[1]]:
          (lu1,lu2,lu3) = ago.ago(mid_to_lastuse[x[1]],now)
          lu2 += " ago"
          sorttime = mid_to_lastuse[x[1]]
      else:
        # Maybe it's a door?
        d = Logs.query.filter((Logs.event_type == eventtypes.RATTBE_LOGEVENT_MEMBER_ENTRY_ALLOWED.id) & (Logs.resource_id == res_id) & (Logs.member_id == x[1])).order_by(Logs.time_logged.desc()).limit(1).one_or_none()
        if d:
          (lu1,lu2,lu3) = ago.ago(d.time_logged,now)
          lu2 += " ago"
          sorttime = d.time_logged
      accrec.append({'member_id':x[1],'member':x[2],'level':level,'permissions':x[5],
          'sortlevel':int(x[3]),
          'sorttime':sorttime,
          'logurl':url_for("logs.logs")+"?input_member_%s=on&input_resource_%s=on" %(x[1],res_id),
          'lockout_reason':'' if x[4] is None else x[4],'lastusedago':lu1,'usedago':lu2,'lastused':lu1})
      
    return render_template('resource_users.html',resource=rid,accrecs=sorted(accrec,key=cmp_to_key(showuser_sort)))


def end_of_month(date):
    date =  date.replace(hour=23,minute=59,second=59,microsecond=999999)
    if date.month == 12:
        return date.replace(day=31)
    return(date.replace(month=date.month+1, day=1) - datetime.timedelta(days=1))


# month, year = previous_month()
def previous_month():
    today = datetime.date.today()
    first_day_of_this_month = today.replace(day=1)
    last_day_of_last_month = first_day_of_this_month - datetime.timedelta(days=1)
    return last_day_of_last_month.month, last_day_of_last_month.year


# bill_member_for_resource
# Params:
#   doBilling: True to actualy bill and collect to Stripe - False to just display
# Returns: (debug,error,tabledata,userdata)
#   debug: Array of debug strings
#   Error: Errror string on failure or None if no error
#   tabledata: Dict(below) containing result for this user-period (i.e. Totals)
#   userdata: List of dicts - each billed line item

def bill_member_for_resource(member_id,res,doBilling,month,year):
    tabledata = {
            "member":"??",
            "member_id":"??",
            "time":"",
            "invoice":"",
            "number":"",
            "price":"",
            "empty":True,
            "status":"None"
            }
    error = None
    disposition=None
    debug = []
    startDate = datetime.datetime(month=int(month),year=int(year),day=1)
    endDate = end_of_month(startDate)
    m = Member.query.filter(Member.id == member_id)
    m = m.join(Subscription,Subscription.member_id == Member.id)
    m = m.add_column(Subscription.customerid)
    m = m.add_column(Subscription.rate_plan)
    m = m.one_or_none()
    debug.append(f"Bill member {member_id} for month {month} year {year}")
    if m is None:
        return ([],f"Member {member_id} not found",tabledata,[])
    member = m.Member
    cid = m.customerid
    iamPro = True if m.rate_plan in ('pro', 'produo') else False
    billdates={}
    usageRecords=[]
    seconds=0
    debug.append(f"Distinct User {member_id} {member.member} RatePlan={m.rate_plan} Pro={iamPro}")
    name = member.member

    tabledata['member']=name
    tabledata['member_id']=member.id
    # Query Prior Invoices
    alreadyBilled=False
    invoiceStatus=None
    if cid is not None and cid != "":
        invoices = query_invoices(cid,res.short,f"{month}/{year}")
        count=0
        for i in invoices:
            debug.append(f" -- Already Billed {i.amount_due} {i.status} {i.description} {i.status_transitions.finalized_at} charge {i.charge} metadata {i.metadata} invoice {i.id} number {i.number}")
            tabledata['invoice']=i.id
            tabledata['number']=i.number
            invoiceStatus = i.status
            count +=1
            alreadyBilled=True
        if (count > 1):
            invoiceStatus = "<Multple!>"
            debug.append(f" -- ERROR multiple outstanding invoices found!")


    # Calculate General Parameters for billing

    billMe = doBilling

    # Query this user's stuff

    debug.append(f" -- Query between {startDate} - {endDate}")
    logs = UsageLog.query.filter((UsageLog.resource_id == res.id) & 
        (UsageLog.member_id == member_id) & 
        (UsageLog.time_reported >= startDate) &
        (UsageLog.time_reported <= endDate)
        ).all()

    freeSecs = 0
    if iamPro and res.free_min_pro is not None:
        freeSecs = res.free_min_pro * 60
    elif (not iamPro) and res.free_min is not None:
        freeSecs = res.free_min * 60

    # If we have no prior, bill for everything
    # If we have prior, bill only after that
    lastUsage=""
    userdata=[]
    totalCents=0
    t={}
    for l in logs:
        if (l.activeSecs > 0):
            t = {}
            secs = l.activeSecs
            if ((l.payTier != 1) or (l.payTier is None)):
                t['info'] = ""

                # Compensate for free time
                if (freeSecs >= secs):
                    t['info']="Free Allotment"
                    secs=0
                    freeSecs -= secs
                elif (freeSecs > 0):
                    t['info']="Partial Free Allotment"
                    secs = secs - freeSecs
                    freeSecs = 0

                if iamPro:
                    cents = int((res.price_pro * secs)/3600)
                else:
                    cents = int((res.price * secs)/3600)

                t['price'] = f"${cents/100:0.2f}"

                totalCents += cents
                seconds += secs
            else:
                t['info'] = "Free Tier"
            datestr = l.time_logged.strftime("%b-%d-%Y")
            if datestr not in billdates: billdates[datestr] = 0
            billdates[datestr] += secs
            usageRecords.append(l.id)
            debug.append(f" -- Logged {l.time_logged} ActiveSecs={l.activeSecs} Tier={l.payTier}")
            datestr = l.time_logged.strftime("%b-%d-%Y %-I:%M %p")
            t['date'] = datestr
            t['log_id'] = l.id
            t['time'] = sec_to_hms(l.activeSecs)
            t["freeTier"] = False if l.payTier != 1 else True
            userdata.append(t)

    tabledata['time'] = sec_to_hms(seconds)

    stripedesc = f"{res.short} Usage: "+(", ".join([f"{x}={int(billdates[x]/60)}min" for x in billdates]))
    tabledata['price']=f"${totalCents/100:0.2f}"
    if (totalCents < 100): 
        billMe = False
        disposition = "Below Minimum"
        tabledata['status']="Below Minimum"
    elif alreadyBilled == True:
        disposition = "Already Billed"
        tabledata['status']="AlreadyBilled: "+invoiceStatus
    elif billMe == False:
        disposition = "Should Bill"
        tabledata['status']="Should Bill"
    elif disposition is None:
        disposition = "Bill"
        tabledata['status']="Billing"


    if ((seconds == 0) and (totalCents == 0)):
        tabledata['empty'] = True
    else:
        tabledata['empty'] = False

    debug.append(f" -- {'Do' if billMe else 'Dont'} Disposition={disposition} {member_id} for {seconds} seconds Seconds={seconds} Desc: {stripedesc} Cents:{totalCents} ")
    if (disposition == "Bill"):
        invoiced=False
        paid=False
        pay=None
        # Do Stripe Payment
        stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','VendingToken')
        commentstr="Billing"
        try:
            price = stripe.Price.create(
              unit_amount=totalCents,
              currency='usd',
              product=res.prodcode)

            invoice = stripe.Invoice.create(
            customer=cid,
            description=stripedesc,
            pending_invoice_items_behavior="exclude",
            #auto_advance=False,
            #collection_method="charge_automatically",
            metadata = {
                'X-MIL-resource':res.short,
                'X-MIL-period':f"{month}/{year}",
                'X-MIL-resource-usage':res.short,
                'X-MIL-last-usage':lastUsage,
                'X-MIL-usageRecords':str(usageRecords)
                }
            )
            invoiceItem = stripe.InvoiceItem.create(customer=cid, price=price, description=stripedesc,invoice=invoice.id) 

            finalize=stripe.Invoice.finalize_invoice(invoice)
            logmsg = f"Invoiced {invoice.id} for ${totalCents/100.0:0.2f}"
            tabledata['invoice']=str(invoice.id)
            authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_USE_BILLED.id,resource_id=res.id,member_id=member_id,message=logmsg,commit=0)
            if (finalize['status'] != 'open'):
                #result = {'error':'success','description':"Stripe Error"}
                error = "Stripe Finalize error for {0} status is {1} productId {2} customerId {3} Invoice {4}".format(name,pay['status'],res.prodcode,cid,invoice.id)
                tabledata['status']="Finalize Error"
            else:
                invoiced=True
                try:
                    pay = stripe.Invoice.pay(invoice)
                    debug.append(f" -- Invoice {invoice.id} paid ${totalCents/100.0:0.2f}")
                except BaseException as e:
                    logmsg = f"Invoice {invoice.id} Error {e}"
                    authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_BILL_FAILED.id,resource_id=res.id,member_id=member_id,message=logmsg,commit=0)
                    error = "Stripe Payment error for {0} Invoice {1}".format(name,invoice.id)
                    tabledata['status']=f"Stripe Pay Error {str(e)}"
                else:
                    if (pay['status'] != 'paid'):
                        paid=False
                        error = f"Payment returned bad status {pay['status']}"
                        tabledata['status']=f"Bad Status {pay['status']}"
                        authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_BILL_FAILED.id,resource_id=res.id,member_id=member_id,message=logmsg,commit=0)
                    else:
                        paid=True
                        tabledata['status']="Paid"
        except BaseException as e:
            logmsg = f"Error: {e}"
            tabledata['status']=f"Exception Error {str(e)}"
            authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_BILL_FAILED.id,resource_id=res.id,member_id=member_id,message=logmsg,commit=0)

        db.session.commit()
        # End Invoiced
    return (debug,error,tabledata,userdata)

def query_specific_invoice(customer_id,resource_short,monthYear=None):
    error = None
    debug = []
    stripe.api_version = '2020-08-27'
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','VendingToken')
    # Status can be "open" or "paid"
    # https://stripe.com/docs/search#search-query-language
    invoices = stripe.Invoice.search(query=f"metadata[\"X-MIL-resource\"]:\"{resource_short}\" AND customer:\"{customer_id}\" AND metadata[\"X-MIL-period\"]:\"{monthYear}\"")
    return invoices


def query_invoices(customer_id,resource_short,monthYear=None):
    error = None
    debug = []
    stripe.api_version = '2020-08-27'
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','VendingToken')
    # Status can be "open" or "paid"
    # https://stripe.com/docs/search#search-query-language
    if monthYear is not None:
        invoices = stripe.Invoice.search(query=f"metadata[\"X-MIL-resource\"]:\"{resource_short}\" AND customer:\"{customer_id}\" AND metadata[\"X-MIL-period\"]:\"{monthYear}\"")
    else:
        invoices = stripe.Invoice.search(query=f"metadata[\"X-MIL-resource\"]:\"{resource_short}\" AND customer:\"{customer_id}\"")

    ### WARNING - DELETE ALL!
    #invoices = stripe.Invoice.list()
    #for invoice in invoices.data:
    #    try:
    #        stripe.Invoice.delete(invoice.id)
    #    except:
    #        pass

    return invoices

def cli_queryresourceinvoice(cmd,**kwargs):
    print (f"CMD IS {cmd}")
    stripe.api_version = '2020-08-27'
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','VendingToken')
    # Status can be "open" or "paid"
    # https://stripe.com/docs/search#search-query-language
    invoice = stripe.Invoice.retrieve(cmd[1])
    print (invoice)

def cli_refundinvoice(cmd,**kwargs):
    print (f"CMD IS {cmd}")
    stripe.api_version = '2020-08-27'
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','VendingToken')
    # Status can be "open" or "paid"
    # https://stripe.com/docs/search#search-query-language
    invoice = stripe.Invoice.retrieve(cmd[1])
    if invoice is not None:
        print (f"Invoice {invoice.id} {invoice.number} status {invoice.status} metadata {invoice.metadata} Total {invoice.total/100.00} Charge {invoice.charge}")
        #charge = stripe.Charge.retrieve(invoice.charge)
        #print (charge)

def secsToHMS(seconds):
    r = ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    if hours > 0:
        r = f"{hours} Hour{'s' if hours > 1 else ''}"
    if minutes > 0:
        r += f" {minutes} Min{'s' if minutes > 1 else ''}"
    if (seconds > 0) or (r==""):
        r += f" {seconds} Sec{'s' if seconds > 1 else ''}"
    return r

@blueprint.route('/billableResources', methods=['GET'])
@login_required
@roles_required(['Admin','Finance'])
def billable_resources():
    resources = AccessByMember.query.filter(current_user.id == AccessByMember.member_id)
    resources = resources.join(Resource,((AccessByMember.resource_id == Resource.id) & ((Resource.price > 0) | (Resource.price_pro > 0))))
    resources = resources.add_column(Resource.name)
    resources = resources.all()
    return render_template('list.html',resources=resources)

@blueprint.route('/<string:resource>/billingUsage', methods=['GET','POST'])
@login_required
@roles_required(['Admin','Finance'])
def billing_usage(resource):
    now = datetime.datetime.now()
    month = now.month
    year = now.year
    if 'month' in request.form: month = int(request.form['month'])
    if 'year' in request.form: year = int(request.form['year'])

    tabledata=[]
    doBilling = False
    if 'Update' in request.form:
        for x in request.form:
            if x.startswith("change_"):
                xx = int(x.replace("change_",""))
                toval = 0 if request.form[x] == "makeFalse" else 1
                ul = UsageLog.query.filter((UsageLog.id ==xx)).one_or_none()
                ul.payTier = toval;
        db.session.commit()

    errors = []
    debug=[]
    rid = (resource)
    res = Resource.query.filter(Resource.name == rid).one_or_none()
    if not res:
      flash ("Resource not found","warning")
      return redirect(url_for('resources.resources'))

    if (not current_user.is_specific_arm(resource=res)):
        flash("Forbidden","Danger")
        return redirect(url_for('index'))

    if (res.price == 0) or (res.prodcode is None) or (res.prodcode.strip()==""):
      flash ("Non-Billable Resource","warning")
      return redirect(url_for('resources.resources'))

    names = {}
    for m in Member.query.all():
        names[m.id]=f"{m.firstname} {m.lastname}"

    ul = UsageLog.query.filter((UsageLog.resource_id == res.id)).order_by(UsageLog.time_logged.desc()).limit(100).all()
    for l in ul:
        (lu1,lu2,lu3) = ago.ago(l.time_logged,now)
        tabledata.append({
            "id":l.id,
            "who": names[l.member_id] if l.member_id in names else "??",
            "when": lu1,
            "ago": f"{lu2} Ago",
            "usage": secsToHMS(l.activeSecs),
            "tier": False if l.payTier != 1 else True
            })
    meta = {
            'first':'',
            'last':'?last'
            }
    return render_template('view_usage.html',resource=res,debug=debug+['Errors:']+errors,table=tabledata,meta=meta,month=month,year=year)

@blueprint.route('/<string:resource>/mybilling/<int:month>/<int:year>', methods=['GET','POST'])
@login_required
def mybillingmon(resource,month,year):
    return billingdetail(resource,current_user.id,month,year)

@blueprint.route('/<string:resource>/mybilling', methods=['GET','POST'])
@login_required
def mybilling(resource):
    return billingdetail(resource,current_user.id)

@blueprint.route('/<string:resource>/userbilling/<int:member_id>', methods=['GET','POST'])
@login_required
def userbilling(resource,member_id):
    rid = (resource)
    res = Resource.query.filter(Resource.name == rid).one_or_none()
    if not res:
      flash ("Resource not found","warning")
      return redirect(url_for('index'))

    if (not current_user.is_specific_arm(resource=res)):
        flash("Forbidden","Danger")
        return redirect(url_for('index'))
    return billingdetail(resource,member_id)

# Generic for single user to see their own, or for ARM to see anyones
def billingdetail(resource,member_id,month=None,year=None):
    now = datetime.datetime.now()
    if month is None: month = now.month
    if year is None: year = now.year
    errors = []
    debug=[]
    if 'month' in request.form: month = int(request.form['month'])
    if 'year' in request.form: year = int(request.form['year'])
    member = Member.query.filter(Member.id == member_id).one()
    res = Resource.query.filter(Resource.name == resource).one_or_none()
    if not res:
      flash ("Resource not found","warning")
      return redirect(url_for('resources.resources'))

    if (res.price == 0) or (res.prodcode is None) or (res.prodcode.strip()==""):
      flash ("Non-Billable Resource","warning")
      return redirect(url_for('resources.resources'))

    (debug,error,tabledata,userdata) = bill_member_for_resource(member_id,res,False,month,year)

    userdata.append({
        'date':"<b>Total</b>",
        'time':tabledata['time'],
        'price':tabledata['price']
        })

    name = f"{member.firstname} {member.lastname}"
    period = f"{month}/{year}"

    s = Subscription.query.filter(Subscription.member_id == member.id).one()
    iv = query_specific_invoice(s.customerid,res.short,period)
    invoices = []
    for i in iv:
        invoices.append({
            'number':i.number,
            'status':i.status,
            'unit_amount':f"${i.amount_due/100:0.2f}",
            'created':datetime.datetime.fromtimestamp((i['created']))
            })


    if (request.args.get("debug") is None): debug=[]

    if (len(errors) > 0):
        debug += ['Errors:']+errors
    isARM = accesslib.user_privs_on_resource(member=current_user,resource=res) >= AccessByMember.LEVEL_ARM
    return render_template('billingdetail.html',resource=res,debug=debug,table=userdata,month=month,year=year,
            invoices=invoices,name=name,period=period,isARM=isARM)


@blueprint.route('/<string:resource>/billing', methods=['GET','POST'])
@login_required
def billing(resource):
    # Did we make changes?
    if request.method == 'POST' and 'Update' in request.form:
        res = Resource.query.filter(Resource.name == resource).one()
        if (not current_user.is_specific_arm(resource=res)):
            flash("Forbidden","Danger")
            return redirect(url_for('index'))
        for x in request.form:
            if x.startswith("change_"):
                xx = int(x.replace("change_",""))
                toval = 0 if request.form[x] == "makeFalse" else 1
                ul = UsageLog.query.filter((UsageLog.id ==xx)).one_or_none()
                ul.payTier = toval;
        db.session.commit()
        flash("Updated","Danger")
        return redirect(url_for('resources.billing',resource=resource))



    now = datetime.datetime.now()
    month = now.month
    year = now.year
    if 'month' in request.form: month = int(request.form['month'])
    if 'year' in request.form: year = int(request.form['year'])

    if 'memberDetail' in request.form:
        return userbilling(resource,request.form['memberDetail'])

    tabledata=[]
    doBilling = False
    if 'invoiceCollect' in request.form:
        doBilling = True
    errors = []
    debug=[]
    debug.append(f"Month {type(month)} {month} Year {type(year)} {year}")
    rid = (resource)
    res = Resource.query.filter(Resource.name == rid).one_or_none()
    if not res:
      flash ("Resource not found","warning")
      return redirect(url_for('resources.resources'))

    if (res.price == 0) or (res.prodcode is None) or (res.prodcode.strip()==""):
      flash ("Non-Billable Resource","warning")
      return redirect(url_for('resources.resources'))

    if (not current_user.is_specific_arm(resource=res)):
        flash("Forbidden","Danger")
        return redirect(url_for('index'))



    users = Logs.query.filter((Logs.resource_id == res.id) & (Logs.event_type == eventtypes.RATTBE_LOGEVENT_RESOURCE_USE_BILLED.id)).order_by(Logs.time_logged.desc()).limit(1).all()
    for u in users:
        debug.append(f"Member ID {u.member_id}")


    # Find all resource users

    if 'viewUsage' in request.form:
        # "My Usage" button - Don't know what this is either
        users = UsageLog.query.filter(UsageLog.resource_id == res.id).distinct().group_by(UsageLog.member_id).all()
        for x in users:
            d,e,t,userdata = bill_member_for_resource(x.member_id,res,False,month,year)
            if (t['empty'] == False):
                tabledata.append(t)
            debug += d
            if e is not None:
                errors.append(e)
    elif 'wtfIsThis' in request.form:
        # User List
        lst = {}
        for l in Logs.query.filter((Logs.resource_id == res.id) & 
            ((Logs.event_type == eventtypes.RATTBE_LOGEVENT_RESOURCE_USE_BILLED.id) | 
            (Logs.event_type == eventtypes.RATTBE_LOGEVENT_RESOURCE_BILL_FAILED.id)) & 
            (Logs.member_id == current_user.id)
            ).order_by(Logs.time_logged.desc()).all():
                #errors.append(f"{l.time_logged} {l.message}")
                lst[l.time_logged] = l
        for e in UsageLog.query.filter((UsageLog.member_id == current_user.id) & (UsageLog.resource_id == res.id)).all():
                lst[e.time_logged] = e
                #errors.append(f"{e.time_logged} {e.activeSecs} {e.payTier}")

        for x in sorted(lst,key = lambda x: x,reverse=True):
            o = lst[x]
            if isinstance(o,UsageLog):
                debug.append(f"UsageLog Time={o.time_logged} Active={o.activeSecs} Tier={o.payTier}")
                tabledata.append({"date":o.time_logged,"data":f" Active={o.activeSecs} Tier={o.payTier}"})
            elif isinstance(o,Logs):
                debug.append(f"BILLED Log {o.time_logged} {o.message}")
                tabledata.append({"date":o.time_logged,"data":f"BILLED {o.message}"})
    else:
        # This is the default and the "Bill Usage" button (doBilling)
        users = UsageLog.query.filter(UsageLog.resource_id == res.id).distinct().group_by(UsageLog.member_id).all()
        for x in users:
            d,e,t,userdata = bill_member_for_resource(x.member_id,res,doBilling,month,year)
            debug += d
            if (t['empty'] == False):
                tabledata.append(t)
            if e is not None:
                errors.append(e)

            if (request.args.get("debug") is None) and ('debug' not in request.form): debug=[]
            if (len(errors)>0):
                debug = debug + ["Errors:"]+errors

        return render_template('bill.html',resource=res,debug=debug,table=tabledata,month=month,year=year)

    if (request.args.get("debug") is None) and ('debug' not in request.form): debug=[]
    if (len(errors)>0):
        debug = debug + ["Errors:"]+errors
    return render_template('resource_billing.html',resource=res,debug=debug,table=tabledata,month=month,year=year)

# Automatic resource billing
def autobill(resname):
    res = Resource.query.filter(Resource.name == resname).one()
    month, year = previous_month()
    users = UsageLog.query.filter(UsageLog.resource_id == res.id).distinct().group_by(UsageLog.member_id).all()
    errors = []
    debug = []
    for x in users:
        d,e,t,userdata = bill_member_for_resource(x.member_id,res,True,month,year)
        if e is not None:
            errors.append(e)
        debug += d
    result = {
            "errors":errors,
            "debug":debug
            }
    return (json_dump(result,indent=2), 200, {'Content-type': 'application/json', 'Content-Language': 'en'})

#TODO: Create safestring converter to replace string; converter?
@blueprint.route('/<string:resource>/log', methods=['GET','POST'])
@roles_required(['Admin','RATT'])
def logging(resource):
   """Endpoint for a resource to log via API"""
   # TODO - verify resources against global list
   if request.method == 'POST':
    # YYYY-MM-DD HH:MM:SS
    # TODO: Filter this for safety
    logdatetime = request.form['logdatetime']
    level = safestr(request.form['level'])
    # 'system' for resource system, rfid for access messages
    userid = safestr(request.form['userid'])
    msg = safestr(request.form['msg'])
    sqlstr = "INSERT into logs (logdatetime,resource,level,userid,msg) VALUES ('%s','%s','%s','%s','%s')" % (logdatetime,resource,level,userid,msg)
    execute_db(sqlstr)
    get_db().commit()
    return render_template('logged.html')
   else:
    if current_user.is_authenticated:
        r = safestr(resource)
        sqlstr = "SELECT logdatetime,resource,level,userid,msg from logs where resource = '%s'" % r
        entries = query_db(sqlstr)
        return render_template('resource_log.html',entries=entries)
    else:
        abort(401)

@blueprint.route('/<string:resource>/maintenance', methods=['POST'])
@login_required
def maintenance_post(resource):
  """(Controller) Display information about a given resource"""
  r = Resource.query.filter(Resource.name==resource).one_or_none()
  if not r:
    flash("Resource not found")
    return redirect(url_for('resources.resources'))

  tool = Tool.query.filter(Tool.name==request.form['tool'])
  tool = tool.filter(Tool.resource_id == r.id).one()

  if accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
    flash("No privilages","danger")
    return redirect(url_for('resources.maintenance',resource=resource))

  if request.form['LogMaint'] == "LogMaint":
    #print (request.form)
    dt = datetime.datetime.strptime(request.form['input_maint_log_datetime'], "%Y-%m-%dT%H:%M")
    #print (dt)
    # ([('tool', u'laser-rabbit'), ('maint', u'optics-all'), ('input_maint_log_datetime', u'2019-03-26T18:00'), ('LogMaint', u'LogMaint')])
    authutil.log(eventtypes.RATTBE_LOGEVENT_TOOL_MAINTENANCE_DONE.id,
      tool_id=tool.id,message=request.form['maint'],doneby=current_user.id,commit=0,when=dt)
    flash("Maintenance recorded","success")
    db.session.commit()
  return redirect(url_for('resources.maintenance',resource=resource))
  
@blueprint.route('/<string:resource>/maintenance', methods=['GET'])
@login_required
def maintenance(resource):
  """(Controller) Display information about a given resource"""
  r = Resource.query.filter(Resource.name==resource).one_or_none()
  tools = Tool.query.filter(Tool.resource_id==r.id).all()
  if not r:
    flash("Resource not found")
    return redirect(url_for('resources.resources'))

  readonly=True
  if accesslib.user_privs_on_resource(member=current_user,resource=r) >= AccessByMember.LEVEL_ARM:
    readonly=False

  tooldata={}
  tools=Tool.query.filter(Tool.resource_id==r.id).all()
  maint=MaintSched.query.filter(MaintSched.resource_id==r.id).all()

  # Find date of last maintenances
  for t in tools:
    tooldata[t.name]={}
    tooldata[t.name]['maint']={}
    for m in maint:
      tooldata[t.name]['maint'][m.name]={}
      tooldata[t.name]['maint'][m.name]['desc']=m.desc

      log = Logs.query.filter(Logs.tool_id == t.id)
      log = log.filter(Logs.event_type == eventtypes.RATTBE_LOGEVENT_TOOL_MAINTENANCE_DONE.id)
      log = log.filter(Logs.message == m.name)
      log = log.order_by(Logs.time_reported)
      log = log.limit(1)
      log = log.one_or_none()

      last_reported=None
      if log and log.time_reported:
        tooldata[t.name]['maint'][m.name]['lastdone']=log.time_reported
        tooldata[t.name]['maint'][m.name]['clock_time_done']=datetime.datetime.now()-log.time_reported
        #print ("CTD IS",tooldata[t.name]['maint'][m.name]['clock_time_done'])
        last_reported = log.time_reported

      # If there is a log entry, find machine time since then
      # if not, find total machine time

      usage = UsageLog.query.filter(UsageLog.tool_id==t.id)
      if (log):
        usage = usage.filter(UsageLog.time_reported > log.time_reported)
      usage = usage.add_column(func.sum(UsageLog.activeSecs).label('activeSecs'))
      usage = usage.one_or_none()

      machine_units=None
      if m.machinetime_span:
        tooldata[t.name]['maint'][m.name]['run_interval']="%s %s" % (m.machinetime_span,m.machinetime_unit)
        activeSecs = usage.activeSecs if usage.activeSecs else 0
        if m.machinetime_unit == "hours":
          tooldata[t.name]['maint'][m.name]['activeTime']="%s Hrs." % int(activeSecs/3600)
          remain_span =  int(m.machinetime_span) - int(activeSecs/3600)
          machine_units="Hrs."
        elif m.machinetime_unit == "minutes":
          tooldata[t.name]['maint'][m.name]['activeTime']="%s Min." % int(activeSecs/60)
          remain_span =  int(m.machinetime_span) - int(activeSecs/60)
          machine_units="Min."
        elif m.machinetime_unit == "days":
          tooldata[t.name]['maint'][m.name]['activeTime']="%s Days" % int(activeSecs/(3600*24))
          remain_span =  int(m.machinetime_span) - int(activeSecs/(3600*24))
          machine_units="Days"
        elif m.machinetime_unit == "weeks":
          tooldata[t.name]['maint'][m.name]['activeTime']="%s Weeks" % int(activeSecs/(3600*24*7))
          remain_span =  int(m.machinetime_span) - int(activeSecs/(3600*24*7))
          machine_units="Weeks"
        elif m.machinetime_unit == "months":
          tooldata[t.name]['maint'][m.name]['activeTime']="%s Months" % int(activeSecs/(3600*24*30))
          remain_span =  int(m.machinetime_span) - int(activeSecs/(3600*24*30))
          machine_units="Months"
        else:
          tooldata[t.name]['maint'][m.name]['activeTime']="%s Sec." % int(activeSecs)
          remain_span =  int(m.machinetime_span) - int(activeSecs)
          machine_units="Sec."
      else:
        activeSecs = usage.activeSecs if usage else 0
        tooldata[t.name]['maint'][m.name]['activeTime']="%s Hrs." % int(activeSecs/3600)

      if machine_units:
        if (remain_span < 0):
          tooldata[t.name]['maint'][m.name]['active_remain']="%s %s <b>OVERDUE</b>" % (-remain_span,machine_units)
        else:
          tooldata[t.name]['maint'][m.name]['active_remain']="%s %s Remaining" % (remain_span,machine_units)

      if m.realtime_span:
        tooldata[t.name]['maint'][m.name]['calendar_interval']="%s %s" % (m.realtime_span,m.realtime_unit)
        if 'clock_time_done' in tooldata[t.name]['maint'][m.name]:
          ctd = tooldata[t.name]['maint'][m.name]['clock_time_done'].total_seconds()
          if m.realtime_unit == "hours":
            ctr=(m.realtime_span-(ctd/3600))
          elif m.realtime_unit == "minutes":
            ctr=(m.realtime_span-(ctd/60))
          elif m.realtime_unit == "days":
            ctr=(m.realtime_span-(ctd/(3600*24)))
          elif m.realtime_unit == "weeks":
            ctr=(m.realtime_span-(ctd/(3600*24*7)))
          elif m.realtime_unit == "months":
            ctr=(m.realtime_span-(ctd/(3600*24*30)))
          elif m.realtime_unit == "years":
            ctr=(m.realtime_span-(ctd/(3600*24*365)))
          else:
            ctr=(m.realtime_span-(ctd))
          if (ctr > 0):
            tooldata[t.name]['maint'][m.name]['clock_time_remaining'] = "{0:.1f} {1} Remaining".format(ctr,m.realtime_unit)
          else:
            tooldata[t.name]['maint'][m.name]['clock_time_remaining'] = "<b>Overdue</b> {0:.1f} {1}".format(-ctr,m.realtime_unit)
          #print "CTA", tooldata[t.name]['maint'][m.name]['clock_time_ago']

      # How long ago when it was done?
      if 'clock_time_done' in tooldata[t.name]['maint'][m.name]:
        ctd = tooldata[t.name]['maint'][m.name]['clock_time_done']
        tooldata[t.name]['maint'][m.name]['clock_time_ago']=ago.ago(datetime.datetime.now()-ctd)[1]
      else:
        tooldata[t.name]['maint'][m.name]['clock_time_ago']="(Never)"
            

  current_datetime=datetime.datetime.strftime(datetime.datetime.now(),"%Y-%m-%dT%H:%M")
  #print ("RETURNING TOOLDATA",tooldata)
  return render_template('maintenance.html',resource=r,readonly=readonly,tools=tools,maint=maint,tooldata=tooldata,current_datetime=current_datetime)

@blueprint.route('/<string:resource>/message',methods=['POST','GET'])
@login_required
def message(resource):
    """(Controller) Update an existing resource from HTML form POST"""
    rname = (resource)
    r = Resource.query.filter(Resource.name==resource).one_or_none()
    if not r:
      flash("Error: Resource not found")
      return redirect(url_for('resources.resources'))
    if accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
      flash("Error: Permission denied")
      return redirect(url_for('resources.resources'))

    if 'Send' in request.form:
      emails=[]
      #print "SENDING",request.form['bodyText']
      bodyText = request.form['bodyText']
      subject = request.form['subject']
      mt_email = True if 'message_type_email' in request.form else False
      mt_alt_email = True if 'message_type_alt_email' in request.form else False
      mt_slack = True if 'message_type_slack_individual' in request.form else False
      mt_slack_group = True if 'message_type_slack_group' in request.form else False
      mt_slack_admin = True if 'message_type_slack_admingroup' in request.form else False
      #print ("RESOURCE",resource)
      #print ("BODY",bodyText)
      #print ("SUBJECT",subject)
      #print ("email",mt_email,"alt_email",mt_alt_email)
      #print ("slack",mt_slack,"slack_group",mt_slack_group,"slack_admin",mt_slack_admin)
      members = Member.query
      members = members.join(AccessByMember,(Member.id == AccessByMember.member_id))
      members = members.join(Subscription,(Subscription.member_id == Member.id))
      members = members.join(Resource,((Resource.name == resource) & (Resource.id == AccessByMember.resource_id )))
      members = members.add_column(Member.member)
      members = members.add_column(Member.email)
      members = members.add_column(Member.alt_email)
      members = members.add_column(Member.slack)
      members = accesslib.addQuickAccessQuery(members)
      members = members.all()

      #print( "SLACK",r.slack_chan)
      #print( "SLACK_ADMIN",r.slack_admin_chan)
      for x in members:
        if x.active in ('Active','Grace Period'): pass #print (x)
        if x.email: emails.append(x.email)
        if x.alt_email: emails.append(x.alt_email)
        if mt_slack and x.slack:
          send_slack_message(x.slack,bodyText)
      #print emails
      if mt_slack_group and r.slack_chan:
        mod=""
        if request.form['slack_group_option']  == "here": mod = "<!here|here> "
        if request.form['slack_group_option']  == "channel": mod = "<!channel> "
        send_slack_message(r.slack_chan,mod+bodyText)
      if mt_slack_admin and r.slack_admin_chan:
        mod=""
        if request.form['slack_admingroup_option']  == "here": mod = "<!here|here> "
        if request.form['slack_admingroup_option']  == "channel": mod = "<!channel> "
        send_slack_message(r.slack_admin_chan,mod+bodyText)
      email_errors=0
      email_ok=0
      for e in emails:
        try:
          genericEmailSender("info@makeitlabs.com",e,subject,bodyText)
        except:
          email_errors += 1
      if email_errors:
        flash("%s email send errors" % email_errors,"warning")
      else:
        flash("Sent %s emails" % (email_ok),"success")
    return render_template('email.html',rec=r)

MAGIC_AUTH_WINDOW_MINUTES = 180  # 3-hour window

def _get_denied_members_for_resource(resource):
    """Return list of Members denied access to this resource within the magic auth window,
    excluding those who already have active access."""
    time_window = datetime.datetime.utcnow() - datetime.timedelta(minutes=MAGIC_AUTH_WINDOW_MINUTES)
    denials = Logs.query.filter(
        Logs.resource_id == resource.id,
        Logs.event_type.in_([
            eventtypes.RATTBE_LOGEVENT_MEMBER_ENTRY_DENIED.id,
            eventtypes.RATTBE_LOGEVENT_MEMBER_KIOSK_DENIED.id,
            eventtypes.RATTBE_LOGEVENT_TOOL_PROHIBITED.id
        ]),
        Logs.time_logged >= time_window
    ).group_by(Logs.member_id).all()

    denied_members = []
    for log in denials:
        existing = AccessByMember.query.filter(
            AccessByMember.member_id == log.member_id,
            AccessByMember.resource_id == resource.id,
            AccessByMember.active == 1,
            AccessByMember.level >= AccessByMember.LEVEL_USER
        ).one_or_none()
        if not existing:
            m = Member.query.filter(Member.id == log.member_id).one_or_none()
            if m:
                denied_members.append(m)
    return denied_members

@blueprint.route('/magic_authorize', methods=['GET'])
@login_required
def magic_authorize():
    """List resources the user is ARM for that have pending denials.
    If exactly one resource qualifies, skip straight to it."""
    if not accesslib.user_is_authorizor(current_user, level=2):
        flash("Unauthorized", "danger")
        return redirect(url_for('index'))

    # Only include resources with pending denials
    resources_with_denials = []
    for r in Resource.query.all():
        if accesslib.user_privs_on_resource(member=current_user, resource=r) >= AccessByMember.LEVEL_ARM:
            if _get_denied_members_for_resource(r):
                resources_with_denials.append(r)

    resources_with_denials = sorted(resources_with_denials, key=lambda x: x.name)

    # Auto-redirect if exactly one resource has pending denials
    if len(resources_with_denials) == 1:
        return redirect(url_for('resources.magic_authorize_resource', resource_id=resources_with_denials[0].id))

    return render_template('magic_authorize.html', resources=resources_with_denials)

@blueprint.route('/magic_authorize/<int:resource_id>', methods=['GET'])
@login_required
def magic_authorize_resource(resource_id):
    """List members who were denied access to this resource in the last 3 hours"""
    if not accesslib.user_is_authorizor(current_user, level=2):
        flash("Unauthorized", "danger")
        return redirect(url_for('index'))

    r = Resource.query.filter(Resource.id == resource_id).one_or_none()
    if not r:
        flash("Resource not found", "warning")
        return redirect(url_for('resources.magic_authorize'))

    if accesslib.user_privs_on_resource(member=current_user, resource=r) < AccessByMember.LEVEL_ARM:
        flash("Unauthorized", "danger")
        return redirect(url_for('resources.magic_authorize'))

    denied_members = _get_denied_members_for_resource(r)
    return render_template('magic_authorize_resource.html', resource=r, denied_members=denied_members)

@blueprint.route('/magic_authorize/<int:resource_id>', methods=['POST'])
@login_required
def magic_authorize_action(resource_id):
    """Authorize the checked users"""
    if not accesslib.user_is_authorizor(current_user, level=2):
        flash("Unauthorized", "danger")
        return redirect(url_for('index'))
        
    r = Resource.query.filter(Resource.id == resource_id).one_or_none()
    if not r:
        flash("Resource not found", "warning")
        return redirect(url_for('resources.magic_authorize'))
        
    if accesslib.user_privs_on_resource(member=current_user, resource=r) < AccessByMember.LEVEL_ARM:
        flash("Unauthorized", "danger")
        return redirect(url_for('resources.magic_authorize'))

    member_ids = request.form.getlist('member_ids')
    count = 0
    for m_id_str in member_ids:
        try:
            m_id = int(m_id_str)
        except ValueError:
            continue
            
        m = Member.query.filter(Member.id == m_id).one_or_none()
        if not m:
            continue
            
        acc = AccessByMember.query.filter(
            AccessByMember.member_id == m.id,
            AccessByMember.resource_id == r.id
        ).one_or_none()
        
        if not acc:
            acc = AccessByMember(
                member_id=m.id,
                resource_id=r.id,
                level=AccessByMember.LEVEL_USER,
                active=1
            )
            db.session.add(acc)
            authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id, resource_id=r.id, member_id=m.id, doneby=current_user.id, message="Magic Authorize", commit=0)
            count += 1
        else:
            if not acc.active or acc.level < AccessByMember.LEVEL_USER:
                acc.active = 1
                if acc.level < AccessByMember.LEVEL_USER:
                    acc.level = AccessByMember.LEVEL_USER
                authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id, resource_id=r.id, member_id=m.id, doneby=current_user.id, message="Magic Authorize (Updated)", commit=0)
                count += 1
                
    if count > 0:
        db.session.commit()
        authutil.kick_backend()
        flash(f"Magic Authorized {count} members for {r.name}", "success")
    else:
        flash("No members were authorized", "warning")
        
    return redirect(url_for('resources.magic_authorize_resource', resource_id=r.id))
def _get_resources():
  q = db.session.query(Resource.name,Resource.owneremail, Resource.description, Resource.id)
  return q.all()

@blueprint.route('/<string:resource>/addnotice', methods=['POST'])
@login_required
def add_notice(resource):
    r = Resource.query.filter(Resource.name==resource).one_or_none()
    if not r:
        flash("Error: Resource not found")
        return redirect(url_for('resources.resources'))
    if accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
        flash("Error: Permission denied")
        return redirect(url_for('resources.resources'))

    from authlibs.db_models import ResourceNotice
    notice = ResourceNotice()
    notice.resource_id = r.id
    notice.title = request.form['input_notice_title'].strip()
    notice.message = request.form['input_notice_message'].strip()
    notice.created_by = current_user.id
    
    if notice.title == "":
        flash("Error: Title is required for a notice")
        return redirect(url_for('resources.resource_show', resource=r.name))

    db.session.add(notice)
    db.session.commit()
    flash("Notice Added", "success")
    return redirect(url_for('resources.resource_show', resource=r.name))

@blueprint.route('/<string:resource>/deletenotice/<int:notice_id>', methods=['POST'])
@login_required
def delete_notice(resource, notice_id):
    r = Resource.query.filter(Resource.name==resource).one_or_none()
    if not r:
        flash("Error: Resource not found")
        return redirect(url_for('resources.resources'))
    if accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
        flash("Error: Permission denied")
        return redirect(url_for('resources.resources'))

    from authlibs.db_models import ResourceNotice
    notice = ResourceNotice.query.filter((ResourceNotice.id == notice_id) & (ResourceNotice.resource_id == r.id)).one_or_none()
    if notice:
        notice.active = False
        db.session.commit()
        flash("Notice deactivated", "success")
    else:
        flash("Notice not found", "warning")
        
    return redirect(url_for('resources.resource_show', resource=r.name))

@blueprint.route('/<string:resource>/acknowledgements', methods=['GET', 'POST'])
@login_required
def resource_acknowledgements(resource):
    r = Resource.query.filter(Resource.name == resource).one_or_none()
    if not r:
        flash("Resource not found")
        return redirect(url_for('resources.resources'))
    if accesslib.user_privs_on_resource(member=current_user, resource=r) < AccessByMember.LEVEL_ARM:
        flash("Permission denied", "warning")
        return redirect(url_for('resources.resources'))
        
    from authlibs.db_models import Acknowledgement, AcknowledgementUser
    import uuid

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            title = request.form.get('title')
            message = request.form.get('message')
            enforce_days = request.form.get('enforce_days')
            
            ack = Acknowledgement(
                resource_id=r.id,
                title=title,
                message=message,
                created_by=current_user.id
            )
            if enforce_days and enforce_days.strip().isdigit():
                ack.enforce_on = datetime.datetime.now() + datetime.timedelta(days=int(enforce_days))
                
            db.session.add(ack)
            db.session.commit()
            authutil.kick_backend()
            flash("Acknowledgement created successfully", "success")
            
        elif action == 'send':
            ack_id = request.form.get('ack_id')
            ack = Acknowledgement.query.filter((Acknowledgement.id == ack_id) & (Acknowledgement.resource_id == r.id)).one_or_none()
            if not ack:
                flash("Acknowledgement not found", "warning")
            else:
                authusers = db.session.query(AccessByMember.member_id).filter(AccessByMember.resource_id == r.id).all()
                member_ids = [u[0] for u in authusers]
                
                existing = db.session.query(AcknowledgementUser).filter(AcknowledgementUser.acknowledgement_id == ack.id).all()
                existing_dict = {e.member_id: e for e in existing}
                
                send_count = 0
                for mid in member_ids:
                    au = existing_dict.get(mid)
                    if au is None:
                        # New user, create record and send
                        token = str(uuid.uuid4())
                        au = AcknowledgementUser(
                            acknowledgement_id=ack.id,
                            member_id=mid,
                            token=token
                        )
                        db.session.add(au)
                    elif au.time_acknowledged is not None:
                        # User has already acknowledged, skip
                        continue
                    
                    # Send email (either new user or pending user)
                    m = Member.query.filter(Member.id == mid).one()
                    link = url_for('api.api_acknowledge', token=au.token, _external=True)
                    email_body = f"Please acknowledge the following notice for {r.name}: {ack.title}\n\n{ack.message}\n\nClick here to acknowledge: {link}"
                    genericEmailSender("info@makeitlabs.com", m.email, ack.title, email_body)
                    send_count += 1
                        
                db.session.commit()
                authutil.kick_backend()
                flash(f"Sent to {send_count} users.", "success")
                
        elif action == 'delete':
            ack_id = request.form.get('ack_id')
            ack = Acknowledgement.query.filter((Acknowledgement.id == ack_id) & (Acknowledgement.resource_id == r.id)).one_or_none()
            if ack:
                db.session.delete(ack)
                db.session.commit()
                authutil.kick_backend()
                flash("Deleted acknowledgement", "success")

    acks = Acknowledgement.query.filter(Acknowledgement.resource_id == r.id).order_by(Acknowledgement.time_created.desc()).all()
    return render_template('resource_acknowledgements.html', resource=r, acks=acks)

@blueprint.route('/<string:resource>/acknowledgements/<int:ack_id>', methods=['GET', 'POST'])
@login_required
def resource_acknowledgement_detail(resource, ack_id):
    r = Resource.query.filter(Resource.name == resource).one_or_none()
    if not r:
        flash("Resource not found")
        return redirect(url_for('resources.resources'))
    if accesslib.user_privs_on_resource(member=current_user, resource=r) < AccessByMember.LEVEL_ARM:
        flash("Permission denied", "warning")
        return redirect(url_for('resources.resources'))

    from authlibs.db_models import Acknowledgement, AcknowledgementUser
    import uuid
    ack = Acknowledgement.query.filter((Acknowledgement.id == ack_id) & (Acknowledgement.resource_id == r.id)).one_or_none()
    
    if not ack:
        flash("Acknowledgement not found")
        return redirect(url_for('resources.resource_acknowledgements', resource=resource))

    if request.method == 'POST':
        action = request.form.get('action')
        member_id = request.form.get('member_id')
        au = AcknowledgementUser.query.filter((AcknowledgementUser.acknowledgement_id == ack.id) & (AcknowledgementUser.member_id == member_id)).one_or_none()
        
        if not au:
            flash("User record not found", "warning")
        elif action == 'resend':
            m = Member.query.filter(Member.id == member_id).one()
            link = url_for('api.api_acknowledge', token=au.token, _external=True)
            email_body = f"Please acknowledge the following notice for {r.name}: {ack.title}\n\n{ack.message}\n\nClick here to acknowledge: {link}"
            genericEmailSender("info@makeitlabs.com", m.email, ack.title, email_body)
            flash("Resent email.", "success")
        elif action == 'manual_ack':
            au.time_acknowledged = datetime.datetime.now()
            db.session.commit()
            authutil.kick_backend()
            flash("Manually acknowledged.", "success")
            
    users = db.session.query(AcknowledgementUser, Member).join(Member).filter(AcknowledgementUser.acknowledgement_id == ack.id).all()
    
    acknowledged = [u for u in users if u[0].time_acknowledged]
    acknowledged.sort(key=lambda u: u[0].time_acknowledged, reverse=True)
    
    unacknowledged = [u for u in users if not u[0].time_acknowledged]
    unacknowledged.sort(key=lambda u: u[1].member)
    
    users = acknowledged + unacknowledged
    
    ack_count = len(acknowledged)
    total_count = len(users)
    
    return render_template('resource_acknowledgement_detail.html', resource=r, ack=ack, users=users, ack_count=ack_count, total_count=total_count)


def register_pages(app):
  graph.register_pages(app)
  app.register_blueprint(blueprint)
