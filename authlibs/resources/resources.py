# vim:shiftwidth=2:noexpandtab

from ..templateCommon import  *

import math
from authlibs import accesslib
from authlibs import ago
from authlibs.comments import comments
from authlibs.slackutils import send_slack_message
import datetime
import graph
from ..google_admin import genericEmailSender

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
	 return render_template('resources.html',resources=resources,access=access,editable=True)

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def resource_create():
	"""(Controller) Create a resource from an HTML form POST"""
	r = Resource()
	r.name = (request.form['input_name'])
	r.short = (request.form['input_short'])
	r.description = (request.form['input_description'])
	r.owneremail = (request.form['input_owneremail'])
	r.slack_chan = (request.form['input_slack_chan'])
	r.slack_admin_chan = (request.form['input_slack_admin_chan'])
	r.info_url = (request.form['input_info_url'])
	r.info_text = (request.form['input_info_text'])
	r.slack_info_text = (request.form['input_slack_info_text'])
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

	return render_template('resource_edit.html',rec=r,readonly=readonly,tools=tools,comments=cc,maint=maint)

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
	print "RESOURCE",resource
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

		r.name = (request.form['input_name'])
		r.short = (request.form['input_short'])
		r.description = (request.form['input_description'])
		r.owneremail = (request.form['input_owneremail'])
		r.slack_chan = (request.form['input_slack_chan'])
		r.slack_admin_chan = (request.form['input_slack_admin_chan'])
		r.info_url = (request.form['input_info_url'])
		r.info_text = (request.form['input_info_text'])
		r.slack_info_text = (request.form['input_slack_info_text'])
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

		authusers = db.session.query(AccessByMember.id,AccessByMember.member_id,Member.member,AccessByMember.level,AccessByMember.lockout_reason)
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
			accrec.append({'member_id':x[1],'member':x[2],'level':level,
					'sortlevel':int(x[3]),
					'sorttime':sorttime,
					'logurl':url_for("logs.logs")+"?input_member_%s=on&input_resource_%s=on" %(x[1],res_id),
					'lockout_reason':'' if x[4] is None else x[4],'lastusedago':lu1,'usedago':lu2,'lastused':lu1})
			
		return render_template('resource_users.html',resource=rid,accrecs=sorted(accrec,cmp=showuser_sort))

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
		print request.form
		dt = datetime.datetime.strptime(request.form['input_maint_log_datetime'], "%Y-%m-%dT%H:%M")
		print dt
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
				print "CTD IS",tooldata[t.name]['maint'][m.name]['clock_time_done']
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
	print "RETURNING TOOLDATA",tooldata
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
			print "RESOURCE",resource
			print "BODY",bodyText
			print "SUBJECT",subject
			print "email",mt_email,"alt_email",mt_alt_email
			print "slack",mt_slack,"slack_group",mt_slack_group,"slack_admin",mt_slack_admin
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

			print "SLACK",r.slack_chan
			print "SLACK_ADMIN",r.slack_admin_chan
			for x in members:
				if x.active in ('Active','Grace Period'): print x
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

def _get_resources():
	q = db.session.query(Resource.name,Resource.owneremail, Resource.description, Resource.id)
	return q.all()

def register_pages(app):
	graph.register_pages(app)
	app.register_blueprint(blueprint)
