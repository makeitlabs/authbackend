#vim:shiftwidth=2:expandtab

from ..templateCommon import  *


import datetime
from ..init import GLOBAL_LOGGER_LOGFILE

# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("belog", __name__, template_folder='templates', static_folder="static",url_prefix="/belog")

modules = ["authserver",
"tools",
"templateCommon",
"smartwaiver",
"resources",
"payments",
"pinpayments",
"cli",
"payments",
"apikeys",
"ubersearch",
"utilities",
"eventtypes",
"logs",
"main_menu",
"belog",
"membership",
"stripe_pay",
"google_user_auth",
"waivers",
"api",
"nodes",
"auth",
"config",
"members",
"dbutil",
"slackutils",
"init",
"kvopts",
"comments",
"reports",
"accesslib",
"db_models",
"google_admin",
"toolauthslack"]
# ------------------------------------------------------------
# Waiver controllers
# ------------------------------------------------------------

@blueprint.route('/', methods=['GET'])
@login_required
def belog():
		logs=[]
		format="html"
		meta={}
		limit=200
		offset=1
		module_filters=[]
		level_filters=[]

		if 'format' in request.values:
			format = request.values['format']
			offset=0
			limit=0
		else:
						if 'limit' in request.values: limit=int(request.values['limit'])
						if 'offset' in request.values: offset=int(request.values['offset'])

		for x in request.values:
			if x.startswith("input_level_"):
				level_filters.append(x.replace("input_level_","").upper())
			if x.startswith("input_module_"):
				module_filters.append(x.replace("input_module_",""))
		

		if (offset <= 0): offset=1
		fd = open(GLOBAL_LOGGER_LOGFILE)

		startdate = None
		enddate = None
		if 'input_date_start' in request.values and request.values['input_date_start'] != "":
				startdate = datetime.datetime.strptime(request.values['input_date_start'],"%m/%d/%Y")
		if 'input_date_end' in request.values and request.values['input_date_end'] != "":
				enddate = datetime.datetime.strptime(request.values['input_date_end'],"%m/%d/%Y")+datetime.timedelta(days=1)
		
		i=1
		count=0
		meta['displayoffset']=offset

		def do_generate():
						for l in reversed(fd.readlines()):
							when=l[0:19]
							sp=l[24:].strip().split(":",4)
							dateok = True
							try:
											dt = datetime.datetime.strptime(when[0:10],"%Y-%m-%d")
											if startdate and dt < startdate: dateok = False
											if enddate and dt > enddate: dateok = False
							except:
								pass
							if sp[0] not in level_filters and sp[1] not in module_filters and dateok:
									yield "\"%s\",\"%s\",\"%s\",\"%s\"\n" %(when,sp[0],sp[1],sp[2])

		if format == "html":
						for l in reversed(fd.readlines()):
							when=l[0:19]
							sp=l[24:].strip().split(":",4)
							if (len( sp) < 3): continue
							if (i>=offset):
								color ="#fff"
								if sp[0]=="WARNING": color="#ffd"
								if sp[0]=="ERROR": color="#fdd"
								if sp[0]=="DEBUG": color="#cff"
								if sp[0]=="CRITICAL": color="#f00"
								dateok = True
								try:
												dt = datetime.datetime.strptime(when[0:10],"%Y-%m-%d")
												if startdate and dt < startdate: dateok = False
												if enddate and dt > enddate: dateok = False
								except:
									pass
					
								if sp[0] not in level_filters and sp[1] not in module_filters and dateok:
									if (limit == 0) or (count < limit):
										logs.append({'when':when,'level':sp[0],'what':sp[1],'color':color,'message':sp[2].strip()})
										meta['lastoffset']=i
										count +=1
							meta['count']=i
							i+=1
		elif format == "csv":
				resp=Response(do_generate(),mimetype='text/csv')
				resp.headers['Content-Disposition']='attachment'
				resp.headers['filename']='log.csv'
				return resp
		else:
				flash ("Invalid format requested","danger")
				return redirect_url(request.url);

		baseurl=url_for("belog.belog")
		filterstr = ("&".join([("%s=1" % x) for x in (module_filters+level_filters)]))
		if filterstr: filterstr = "&"+filterstr
		if limit != 0:
			meta['first'] = baseurl+("?limit=%s&offset=%s" % (limit,"1"))+filterstr
			meta['last'] = baseurl+("?limit=%s&offset=%s" % (limit, meta['count']-limit))+filterstr
			if ((offset+limit) < i) and 'lastoffset' in meta:
				meta['next'] = baseurl+("?limit=%s&offset=%s" % (limit, meta['lastoffset']+1))+filterstr
			if (offset > 1):
				meta['prev'] = baseurl+("?limit=%s&offset=%s" % (limit, offset-limit))+filterstr
		meta['csvurl'] = baseurl+"?format=csv"+filterstr
		
		return render_template('belog.html',logs=logs,meta=meta,modules=sorted(modules))



def register_pages(app):
	app.register_blueprint(blueprint)
