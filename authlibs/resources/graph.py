# vim:shiftwidth=2:noexpandtab

from ..templateCommon import  *

from authlibs import accesslib
from authlibs.comments import comments
from json import dumps as json_dumps
import datetime

blueprint = Blueprint("graphs", __name__, template_folder='templates', static_folder="static",url_prefix="/resource/graphs/api")

# We do some weird stuff here to be able to to determine the "day" - each day gets assigned
# a consecutive inteiger

def daynum(dt):
	return (dt - datetime.datetime(2000,1,1)).days

@blueprint.route('/v1/weekly/<string:id>', methods=['GET'])
@login_required
def weekly(id):
	return graph_by_day(id,7)

def graph_by_day(id,days):
	"""(Controller) Display information about a given resource"""
	tools = Tool.query.filter(Tool.resource_id==id).all()
	r = Resource.query.filter(Resource.id==id).one()

	#if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
	if not current_user.privs('HeadRM','RATT') and not accesslib.user_is_authorizor(member=current_user,level=2):
		return "NOAccess",403

	now = datetime.datetime.now()
	enddate = now
	enddate = enddate.replace(hour=0,minute=0,second=0,microsecond=0)
	startdate = enddate-datetime.timedelta(days=days)
	
	q = UsageLog.query.filter(UsageLog.time_logged>=startdate)
	q = q.filter(UsageLog.time_logged<enddate)
	q = q.order_by(UsageLog.time_logged)
	q = q.filter(UsageLog.resource_id == r.id)
	q = q.all()

	dow=['Mon','Tues','Wed','Thurs','Fri','Sat','Sun']
	short_dow=['M','Tu','W','Th','F','Sa','Su']
	data=[['Day','Enabled','Active','Idle']]
	nowday = daynum(now)
	daydata=[]
	for _ in range (0,days):
		daydata.append({'enabled':0,'active':0,'idle':0})

	for x in q:
		t = x.time_logged
		dn = daynum(t)
		daydelta = nowday-dn
		if ((daydelta <=days) and (daydelta >= 1)):
			daydata[daydelta-1]['enabled'] += x.enabledSecs
			daydata[daydelta-1]['idle'] += x.idleSecs
			daydata[daydelta-1]['active'] += x.activeSecs

	# Write this backwards - i.e. LAST entry is YESTERDAY
	for i in range(days-1,-1,-1):
		x = daydata[i]
		if days==7:
			x['label'] = dow[(now.weekday()-(i+1))%7]
		else:
			dy = startdate-datetime.timedelta(days=i)
			x['label'] = short_dow[dy.weekday()%7] + " "
			x['label'] += str(dy.day)
		data.append([x['label'],x['enabled'],x['active'],x['idle']])

	out={'data':data,'type':'area','opts':{
		'title':"%d day usage"%days,
		'hAxis':{'title': 'Day',  'titleTextStyle': {'color': '#333'}},
		'vAxis': {'minValue': 0}
		}}
	return json_dumps(out,indent=2)

@blueprint.route('/v1/monthly/<string:id>', methods=['GET'])
@login_required
def monthly(id):
	return graph_by_day(id,31)

def unused(id):
	"""(Controller) Display information about a given resource"""
	tools = Tool.query.filter(Tool.resource_id==id).all()
	r = Resource.query.filter(Resource.id==id).one()

	#if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
	if not current_user.privs('HeadRM','RATT') and not accesslib.user_is_authorizor(member=current_user,level=2):
		return "NOAccess",403

	now = datetime.datetime.now()
	enddate = now
	enddate.replace(hour=0,minute=0,second=0,microsecond=0)
	startdate = enddate-datetime.timedelta(days=31)
	q = UsageLog.query.filter(UsageLog.time_logged>=startdate)
	q = q.filter(UsageLog.time_logged<enddate)
	q = q.order_by(UsageLog.time_logged)
	q = q.filter(UsageLog.resource_id == r.id)
	q = q.all()

	dow=['Mon','Tues','Wed','Thurs','Fri','Sat','Sun']
	data=[['Day','Enabled','Active','Idle']]
	now = datetime.datetime.now()
	nowday = daynum(now)
	daydata=[]
	for _ in range (0,30):
		daydata.append({'dom':"??",'enabled':0,'active':0,'idle':0})

	for x in q:
		t = x.time_logged
		dn = daynum(t)
		daydelta = nowday-dn
		if ((daydelta <=30) and (daydelta >= 1)):
			daydata[daydelta-1]['enabled'] += x.enabledSecs
			daydata[daydelta-1]['idle'] += x.idleSecs
			daydata[daydelta-1]['active'] += x.activeSecs
			daydata[daydelta-1]['dom'] = x.time_logged.day

	for x in daydata:
		y= [str(x['dom']),x['enabled'],x['active'],x['idle']]
		data.append(y);
	out={'data':data,'type':'area','opts':{
		'title':"Monthy Usage Data`",
		'hAxis':{'title': 'Day',  'titleTextStyle': {'color': '#333'}},
		'vAxis': {'minValue': 0}
		}}
	return json_dumps(out)

@blueprint.route('/v1/weekUsers/<string:id>', methods=['GET'])
@login_required
def weekUsers(id):
	return userWindowReport(id,7)

@blueprint.route('/v1/monthUsers/<string:id>', methods=['GET'])
@login_required
def monthUsers(id):
	return userWindowReport(id,31)

def userWindowReport(id,days):
	"""(Controller) Display information about a given resource"""
	tools = Tool.query.filter(Tool.resource_id==id).all()
	r = Resource.query.filter(Resource.id==id).one()

	#if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
	if not current_user.privs('HeadRM','RATT') and not accesslib.user_is_authorizor(member=current_user,level=2):
		return "NOAccess",403

	now = datetime.datetime.now()
	enddate = now
	enddate = enddate.replace(hour=0,minute=0,second=0,microsecond=0)
	startdate = enddate-datetime.timedelta(days=days)
	
	q = UsageLog.query.filter(UsageLog.time_logged>=startdate)
	q = q.filter(UsageLog.time_logged<enddate)
	q = q.group_by(UsageLog.member_id)
	q = q.filter(UsageLog.resource_id == r.id)
	q = q.add_column(func.sum(UsageLog.enabledSecs).label('enabled'))
	q = q.add_column(func.sum(UsageLog.idleSecs).label('idle'))
	q = q.add_column(func.sum(UsageLog.activeSecs).label('active'))
	q = q.add_column(UsageLog.member_id.label('memberid'))
	q = q.all()

	data=[]
	totalenabled=0
	for x in q:
		data.append({'member_id':x.memberid,'enabled':x.enabled})
		totalenabled += x.enabled

	out = []
	for x in sorted(data,key=lambda x:x['enabled'],reverse=True):
		out.append(x)

	if len(out)> 10:
		out=out[0:9]
		toptotal=0
		for x in out:
			toptotal += x['enabled']
		out.append({'member_id':0,'enabled':totalenabled-toptotal})

	# Find usernames

	for x in out:
		if x['member_id']==0:
			x['member'] = 'Other Users'
		else:
			x['member'] = Member.query.filter(Member.id == x['member_id']).one().member
	
	out2=[['Member','Enabled']]
	for x in out:
		m  = (int(x['enabled']/60))
		minstr = "%s minutes" % (m)
		if m > 60:
			h= (int(x['enabled']/3600))
			m = (x['enabled']/60) - (h*60)
			minstr = "%s hrs %s minutes" % (h,m)
		out2.append([x['member'],{"v":x['enabled'],"f":minstr}])

	if days == 7:
		title="Weekly top users"
	elif days == 28:
		title="Monthly top users"
	else:
		title = str(days)+" day window"
	
	out={'data':out2,'type':'pie','opts':{
		'title':title,
		'hAxis':{'title': 'Name',  'titleTextStyle': {'color': '#333'}},
		'vAxis': {'minValue': 0}
		}}
	out = json_dumps(out,indent=2)
	return out,200

@blueprint.route('/v1/weekCalendar/<int:id>', methods=['GET'])
@login_required
def weekCalendar(id):
	dow=['Mon','Tues','Wed','Thurs','Fri','Sat','Sun']
	r = Resource.query.filter(Resource.id==id).one()
	#if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
	if not current_user.privs('HeadRM','RATT') and not accesslib.user_is_authorizor(member=current_user,level=2):
		return "NOAccess",403

	days=7
	now = datetime.datetime.now()
	enddate = now
	enddate = enddate.replace(hour=0,minute=0,second=0,microsecond=0)-datetime.timedelta(seconds=1)
	startdate = enddate-datetime.timedelta(days=days)
	q = UsageLog.query
	q = q.filter(UsageLog.time_logged>startdate)
	q = q.filter(UsageLog.time_logged<enddate)
	q = q.filter(UsageLog.resource_id == id)
	q = q.add_column(UsageLog.time_logged.label('time'))
	q = q.add_column(UsageLog.enabledSecs.label('enabled'))
	q = q.add_column(UsageLog.member_id.label('memberid'))
	usage=[]
	weekdays=[]
	for r in range(0,7):	
		weekdays.append(dow[(startdate.weekday()+r)%7])

	startdate = startdate+datetime.timedelta(seconds=1)
	#print "START",startdate
	#print "END",enddate
	#print "MIN SPAN",(enddate-startdate).total_seconds()
	memberids=set()
	usertimes={}
	palettes = [
	"#a7cee2",
	"#2479b2",
	"#b3df8d",
	"#37a032",
	"#f9999a",
	"#e11424",
	"#fcbe74",
	"#fd7e1e",
	"#c9b2d5",
	"#6a3e98",
	"#b0582d"]
	eastern = dateutil.tz.gettz('US/Eastern')
	utc = dateutil.tz.gettz('UTC')
	for x in q.all():
		#print startdate," minus ",x.time," seconds ",((x.time-startdate).total_seconds())
		#print "Delta ",((x.time-startdate))
		#print "Minutes ",int(((x.time-startdate).total_seconds())/60)
		#print "ENABLED SECS ",x.enabled
		localstarttime = x.time.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)
		startmin = int(((localstarttime-startdate).total_seconds())/60)
		endmin = startmin +int(x.enabled/60)
		#print "endmin",endmin
		#print x.time
		innertext="Member "+str(x.memberid)
		memberids.add(x.memberid)
		if x.memberid not in usertimes:
			usertimes[x.memberid]=int(x.enabled)
		else:
			usertimes[x.memberid]+=int(x.enabled)
		a1={'member':x.memberid,'startmin':startmin,'endmin':endmin,'text':innertext,'color':palettes[10]}

		# Handle "midnight wrap - if so -split into two records
		startday = startmin / (60*24)
		endday = endmin / (60*24)
		if startday != endday:
			a1['endmin'] = (60*24)*endday
			newdaystart = a1['endmin']+1
			a2={'member':x.memberid,'startmin':newdaystart,'endmin':endmin,'text':innertext,'color':palettes[10]}
			usage.append(a2)
		usage.append(a1)

	# Add Names
	members = Member.query.filter(Member.id.in_(memberids)).all()
	membernames = {}
	for x in members:
		if x.nickname:
			membernames[x.id]=x.nickname +" "+x.lastname
		else:
			membernames[x.id]=x.firstname +" "+x.lastname
	for u in usage:
		if u['member'] in membernames:
			u['text']=membernames[u['member']]


	legend=[]
	for (i,x) in enumerate(sorted(usertimes,key=lambda y:usertimes[y],reverse=True)[:9]):
		#print x,usertimes[x]
		if x in membernames:
			legend.append({'name':membernames[x],'color':palettes[i]})
		else:
			legend.append({'name':"Member "+str(x),'color':palettes[i]})
		for u in usage:
			if u['member'] == x: u['color'] = palettes[i]

	fd = open(blueprint.static_folder+"/WeekUsage.svg")
	#print json_dumps(usage,indent=2)
	#print json_dumps(legend,indent=2)
	result = json_dumps({"data":fd.read(),"usage":usage,"weekdays":weekdays,'legend':legend})
	return	result,200

def register_pages(app):
	app.register_blueprint(blueprint)
