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

	if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
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

	if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
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
	"""(Controller) Display information about a given resource"""
	tools = Tool.query.filter(Tool.resource_id==id).all()
	r = Resource.query.filter(Resource.id==id).one()

	if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
		return "NOAccess",403

	now = datetime.datetime.now()
	enddate = now
	enddate = enddate.replace(hour=0,minute=0,second=0,microsecond=0)
	startdate = enddate-datetime.timedelta(days=7)
	
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
	for x in sorted(data,key=lambda x:x['enabled']):
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
			x['member'] = 'Total'
		else:
			x['member'] = Member.query.filter(Member.id == x['member_id']).one().member
	
	out2=[['Member','Enabled']]
	for x in out:
		out2.append([x['member'],x['enabled']])

	out={'data':out2,'type':'pie','opts':{
		'title':"Monthy Top Users`",
		'hAxis':{'title': 'Name',  'titleTextStyle': {'color': '#333'}},
		'vAxis': {'minValue': 0}
		}}
	out = json_dumps(out)
	return out,200

@blueprint.route('/v1/weekCalendar/<int:id>', methods=['GET'])
@login_required
def weekCalendar(id):
	dow=['Mon','Tues','Wed','Thurs','Fri','Sat','Sun']
	r = Resource.query.filter(Resource.id==id).one()
	if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
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

	# print "START",startdate
	# print "END",enddate
	# print "MIN SPAN",(enddate-startdate).total_seconds()
	for x in q.all():
		startmin = int(((x.time-startdate).total_seconds())/60)
		endmin = startmin +x.enabled
		usage.append({'member':x.memberid,'startmin':startmin,'endmin':endmin})
	fd = open(blueprint.static_folder+"/WeekUsage.svg")
	result = json_dumps({"data":fd.read(),"usage":usage,"weekdays":weekdays})
	return	result,200

def register_pages(app):
	app.register_blueprint(blueprint)
