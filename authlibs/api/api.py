# vim:tabstop=2:shiftwidth=2:expandtab

from ..templateCommon import *

from authlibs import accesslib

from authlibs.ubersearch import ubersearch
from authlibs import membership
from authlibs import payments
from authlibs.waivers.waivers import cli_waivers,connect_waivers
from authlibs.slackutils import automatch_missing_slack_ids,add_user_to_channel,send_slack_message
from authlibs.members.notices import send_all_notices
from authlibs.autoplot.autoplot import autoplot_api
import slackapi
import base64
import random,string
import tempfile
import subprocess
import datetime


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("api", __name__, template_folder='templates', static_folder="static",url_prefix="/api")


def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def bad_acl():
    """Sends a 403 response """
    return Response(
    'Forbiden - ACL restruction\n',403)

def malformed_acl():
    """Sends a 403 response """
    return Response(
    'Forbiden - Malformed ACL\n',403)


# This is to allow non "member" accounts in via API
# NOTE we are decorating the one we are importing from flask-user
def api_only(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            print "NOT AUTH"
            return error_401()
        a = check_api_access(auth.username, auth.password)
        if not a:
            return authenticate() # Send a "Login required" Error
        #print "CHECK",request.url,request.url_root
        check = request.url.replace(request.url_root,"")
        #print check
        if a.acl:
          for x in a.acl.split("\n"):
            #print "LINE",x
            x = x.strip().lower()
            if x == "deny": 
              logger.warning("ACL denied {0} for {1} url {2}".format(str(x),a.name,str(check)))
              return bad_acl()
            if x == "allow": break
            try:
              (k,v) = x.split(" ",2)
              if k not in ("allow","deny"):
                logger.error("Not allow or deny acl line {0} for {1} url {2}".format(str(x),a.name,str(check)))
                return malformed_acl()
              r = re.match(v,check)
              #print "A",a,"C",c,"G",r
              if r:
                if k == "allow": break
                if k == "deny": 
                  logger.warning("ACL denied {0} for {1} url {2}".format(str(x),a.name,str(check)))
                  return bad_acl()
            except b as BaseException:
              logger.error("Malformed acl line {0} for {1} url {2}".format(str(x),a.name,str(request.url)))
              return malformed_acl()
        
        g.apikey=auth.username
        return f(*args, **kwargs)
    return decorated

def localhost_only(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.environ['REMOTE_ADDR'] != '127.0.0.1':
            return Response(
            'Access via localhost only', 403,
            {'Content-Type': 'text/plain'})
        return f(*args, **kwargs)
    return decorated

def check_api_access(username,password):
    if (current_app.config['globalConfig'].Config.has_option('Slack','SLACKBOT_API_USERNAME') and
      current_app.config['globalConfig'].Config.has_option('Slack','SLACKBOT_API_PASSWORD')):
      if ((current_app.config['globalConfig'].Config.get('Slack','SLACKBOT_API_USERNAME') == username) and
        (current_app.config['globalConfig'].Config.get('Slack','SLACKBOT_API_PASSWORD') == password)):
        pass #return a
    a= ApiKey.query.filter_by(username=username).one_or_none()
    if not a:
        return None
    if not a.password:
        return None
    if current_app.user_manager.verify_password( password,a.password):
        return a
    else:
        return None

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

@blueprint.route('/v1/reloadacl', methods=['GET'])
@api_only
def api_v1_reloadacl():
		authutil.kick_backend()
		return json_dump({'status':'success'}), 200, {'Content-type': 'application/json'}

@blueprint.route('/test/localhost', methods=['GET'])
@localhost_only
def test_localhost():
		return "Success", 200, {'Content-type': 'text/plain'}

@blueprint.route('/v1/whoami', methods=['GET'])
@api_only
def whoami():
		return json_dump("You have a valid API key %s" % g.apikey, 200, {'Content-type': 'text/plain'})

@blueprint.route('/v1/node/<string:node>/config', methods=['GET'])
@api_only
def api_v1_nodeconfig(node):
		result = {'status':'success'}
		n = Node.query.filter(Node.name == node).one_or_none()
		if not n:
			result['status']='error'
			result['message']='Node not found'
			return json_dump(result, 200, {'Content-type': 'text/plain'})

		result['mac']=n.mac
		result['name']=n.name

		kv = KVopt.query.add_column(NodeConfig.value).outerjoin(NodeConfig,((NodeConfig.node_id == n.id) & (NodeConfig.key_id == KVopt.id))).all()
		result['params']={}
		for (k,v) in kv:
			#print "KEy %s Value %s Default %s"%(k.keyname,v,k.default)
			sp = k.keyname.split(".")
			val=""
			if v: 
				val = v
			else:
				val = k.default
			if val is None: val=""
			if k.kind.lower() == "boolean":
				if not v:
					val = False
				elif v.lower() in ('on','yes','true','1'):
					val=True
				else:
					val=False
			elif k.kind.lower() == "integer":
				try:
					val=int(v)
				except:
					val=0
			
			i = result['params']
			for kk in sp[:-1]:
				if kk not in i:
					i[kk]={}
				i=i[kk]
				
			i[sp[-1]]=val

		result['tools']=[]
		tools= Tool.query.add_columns(Resource.name).add_column(Resource.id)
		tools = tools.filter(Tool.node_id==n.id).join(Resource,Resource.id==Tool.resource_id)
		tools = tools.all()
		for x in tools:
			(t,resname,rid) =x
			tl={}
			tl['name']=t.name
			tl['resource_id']=rid
			tl['resource']=resname
			tl['id']=t.id
			tl['lockout']=t.lockout
			result['tools'].append(tl)

		#print json_dump(result,indent=2)
		return json_dump(result, 200, {'Content-type': 'application/json', 'Content-Language': 'en'},indent=2)

@blueprint.route('/v1/slack/admin/<string:slackid>',methods=['POST'])
@api_only
@localhost_only
def api_slack_admin(slackid):
  r = Member.query.filter(Member.slack == slackid).all()
  if len(r)>1:
    output = "You could be one of several possible matching members:\n\n"
    for x in r:
      output += "%s\n" % x.member
    output += "\nPlease ask an admin to help sort this out."
    logger.error("slack id %s matching several members." % slackid)
    return output
  elif len(r) == 0:
    output = "I am unable to match a member record to your slack ID. lease contact an admin to sort this out."
    logger.error("slack id %s has no matching member." % slackid)
    return output
  data=request.get_json()
  return slackapi.slack_admin_api(data['command'],r[0]) , 200, {'Content-Type': 'text/plain', 'Content-Language': 'en'}

# See which tools a user can request access to
@blueprint.route('/v1/slack/tools/<string:slackid>',methods=['GET'])
@api_only
@localhost_only
def api_slack_tools(slackid):
  t = db.session.query(Tool)
  t = t.join(Member,Member.slack == slackid)
  t = t.join(AccessByMember,((AccessByMember.member_id == Member.id) & (Tool.resource_id == AccessByMember.resource_id)))

  result=""
  for x in t.all():
    if x.short:
      result += "`%s` (or `%s`)\n" % (x.name,x.short)
    else:
      result += "`%s`\n" % x.name
  return result, 200, {'Content-Type': 'text/plain', 'Content-Language': 'en'}

@blueprint.route('/v1/slack/open/<string:tool>/<string:slackid>',methods=['GET'])
@api_only
@localhost_only
def api_slack_open(tool,slackid):
  r = Member.query.filter(Member.slack == slackid).all()
  if len(r)>1:
    output = "You could be one of several possible matching members:\n\n"
    for x in r:
      output += "%s\n" % x.member
    output += "\nPlease ask an admin to help sort this out."
    logger.error("slack id %s matching several members." % slackid)
  elif len(r) == 0:
    output = "I am unable to match a member record to your slack ID. lease contact an admin to sort this out."
    logger.error("slack id %s has no matching member." % slackid)
  else:
    q=Tool.query.filter(((Tool.name.ilike(tool)) | (Tool.short.ilike(tool))))
    q = q.join(Resource,Tool.resource_id == Resource.id).add_column(Resource.description)
    q = q.join(Node,Node.id == Tool.node_id).add_column(Node.mac)
    q = q.outerjoin(AccessByMember,((AccessByMember.resource_id == Resource.id) & (AccessByMember.member_id == r[0].id))).add_column(AccessByMember.level)
    q = q.one_or_none()

    if q is None:
       output = "No tool/resource by that name found"
       return output, 200, {'Content-Type': 'application/json', 'Content-Language': 'en'}

    (tool,resource,node,access) = q
    if access is None and not r[0].privs('HeadRM'):
      output = "You do not have access to %s" % resource
    else:
      code = ''.join(random.choice(string.digits) for _ in range(4))
      authutil.send_tool_unlock(tool.name,r[0],node,access,code)
      output = "Access granted -  Enter this temporary code into RATT: %s\n(Expires in 3 minutes)" % (code)
  return output, 200, {'Content-Type': 'text/plain', 'Content-Language': 'en'}
  

@blueprint.route('/v1/slack/whoami/<string:slackid>',methods=['GET'])
@api_only
@localhost_only
def api_slack_whoami(slackid):
  r = Member.query.filter(Member.slack == slackid).all()
  if len(r)>1:
    output = "You could be one of several possible matching members:\n\n"
    for x in r:
      output += "%s\n" % x.member
    output += "\nPlease ask an admin to help sort this out."
    logger.error("slack id %s matching several members." % slackid)
  elif len(r) == 0:
    output = "I am unable to match a member record to your slack ID. lease contact an admin to sort this out."
    logger.error("slack id %s has no matching member." % slackid)
  else:
    m = r[0]
    output = "You are %s %s (%s)\n" % (m.firstname,m.lastname,m.member)
    output += "Email: %s\n" % m.email
    output += "Your membership status: *%s*\n" % accesslib.quickSubscriptionCheck(member_id=m.id)
    au = AccessByMember.query.filter(AccessByMember.member_id==m.id).join(Resource,AccessByMember.resource_id == Resource.id)
    au = au.add_column(Resource.name).all()

    if m.access_enabled == 0:
      if not m.access_reason:
        output += "\n:no_access:Your lab access is on hold, pending acceptance of the Waiver\n\n";
      else:
        output += "\n:warning: Your lab access is suspended because: %s \n\n" % m.access_reason;
    has_frontdoor=False
    output +="\n"
    for a in au:
      level = AccessByMember.LEVEL_NOACCESS
      if m.privs('HeadRM'): level = AccessByMember.LEVEL_HEADRM
      else: level = a[0].level
      if level > AccessByMember.LEVEL_USER:
        output += ":ballot_box_with_check: You have %s access to %s\n" % (accessLevelToString(level),a[1])
      else:
        output += ":ballot_box_with_check: You have access to %s\n" % a[1]
      if a[1] == "frontdoor": has_frontdoor = True

    output +="\n"

    if not has_frontdoor:
      output += "\n:lock: You need to complete orientation before being granted door access\n"

    for r in UserRoles.query.filter(UserRoles.member_id == m.id).join(Role,Role.id == UserRoles.role_id).add_column(Role.name).all():
      (ur,role) = r
      output += ":star: You have global \"%s\" privileges\n" % role
    
  return output, 200, {'Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/membersearch/<string:searchstr>',methods=['GET'])
@api_only
@localhost_only
def api_member_search_handler(searchstr):
  output  = json_dump(ubersearch(searchstr,only=['members'],membertypes=['Active']),indent=2)
  return output, 200, {'Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/v1/kiosklog', methods=['OPTIONS'])
#@api_only
def api_v1_kiosklog_options():
		return "", 200, {
                        'Access-Control-Allow-Origin':'https://plachenko.github.io',
                        'Access-Control-Allow-Headers':'Content-Type,Authorization',
                        'Access-Control-Allow-Credentials':'true',
                        'Access-Control-Allow-Methods':'OPTIONS,GET',
                        'Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/v1/tempauth', methods=['POST'])
@api_only
def api_v1_tempauth():
  data=request.get_json()
  print "REQUEST",request
  print "DATA",data
  if not data:
		return json_dump({'result':'failure','reason':'Not JSON request'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

  tag = None
  resource = None
  if 'fobid' not in data:
		return json_dump({'result':'failure','reason':'No Fob ID specified'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

  if 'resource' not in data:
		return json_dump({'result':'failure','reason':'No resource specified'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

  print "FINDING RAW FOB",data['fobid']
  tag = MemberTag.query.filter(MemberTag.tag_ident == data['fobid']).one_or_none()

  if tag is None:
		return json_dump({'result':'failure','reason':'Fob not found'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

  resource = Resource.query.filter(Resource.name == data['resource']).one_or_none()
  if resource is None:
		return json_dump({'result':'failure','reason':'Resource not found'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}
  

  ta = TempAuth.query.filter((TempAuth.member_id == tag.member_id) & (TempAuth.resource_id == resource.id)).all()

  print "QUERIED",ta,"Member",tag.member_id,"RESOURCE",resource.id,ta
  if ta:
    ta = ta[0]
    if ta.expires < datetime.datetime.now():
      db.session.delete(ta)
      db.session.commit()
      return json_dump({'result':'failure','reason':'Time Expired'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}
    if ta.timesallowed <= 0:
      db.session.delete(ta)
      db.session.commit()
      return json_dump({'result':'failure','reason':'Count Expired'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

    ta.timesallowed -= 1
    if (ta.timesallowed <= 0):
      db.session.delete(ta)
    db.session.commit()
    
  print ta

  if not ta:
		return json_dump({'result':'failure','reason':'No Access'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

	return json_dump({'result':'success','reason':'Access Allowed'}), 200, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

@blueprint.route('/v1/kiosklog', methods=['POST'])
@api_only
def api_v1_kiosklog():
  data=request.get_json()
  #print "REQUEST",request
  #print "DATA",data
  if not data:
		return json_dump({'result':'failure','reason':'Not JSON request'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}
  
  if 'user' not in data or 'event' not in data:
		return json_dump({'result':'failure','reason':'Field missing'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

  
  imagename=""
  imagecode=None
  if 'visibleimage' in data:
    try:
      img = base64.b64decode(data['visibleimage'])
      tf = tempfile.NamedTemporaryFile(dir="authlibs/logs/static/kioskimages",suffix='.jpg',delete=False)
      tf.write(img)
      imagename=tf.name
      tf.flush()
      tf.close()
      nf = imagename.replace(".jpg","_ir.jpg")
      ff = open(nf,"w")
      img_ir = base64.b64decode(data['irimage'])
      ff.write(img_ir)
      ff.close()
      imagecode = imagename.split("/")[-1].replace(".jpg","")
      imagename = "kioskimages:"+imagename.split("/")[-1].replace(".jpg","")
    except BaseException as e:
      print e
      pass
  m = Member.query.filter(Member.member==data['user']).one_or_none()
  if not m:
		return json_dump({'result':'failure','reason':'Member not found'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

  e=None
  icon=""
  if data['event'] == 'ACCEPTED':
    e = eventtypes.RATTBE_LOGEVENT_MEMBER_KIOSK_ACCEPTED.id
    icon = ":white_check_mark:"
  elif data['event'] == 'DENIED':
    e = eventtypes.RATTBE_LOGEVENT_MEMBER_KIOSK_DENIED.id
    icon = ":x:"
  elif data['event'] == 'FAILED':
    e = eventtypes.RATTBE_LOGEVENT_MEMBER_KIOSK_FAILED.id
    icon = ":bangbang:"
  else:
		return json_dump({'result':'failure','reason':'Bad event type'}), 400, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

  authutil.log(e,member_id=m.id,message=imagename,commit=0)
  db.session.commit()
  cv_status=-1
  cv_error="???"
  try:
    cam_slackchan = current_app.config['globalConfig'].Config.get('cameras','slackchan')
    s = subprocess.Popen(['/var/www/covosk-cv/covid-mask-detector/testone.py',imagecode],stdout=subprocess.PIPE)
    txt = s.stdout.read().strip()
    res = s.wait()
    cv_status = res
    cv_error = txt
    json.dump({'txt':txt,'res':res},open("authlibs/logs/static/kioskimages/"+imagecode+".json","w"))
    if (res != 0):
       url="https://auth.makeitlabs.com"+url_for("logs.kioskentry",ke=imagecode)
       res = send_slack_message(
              "#project-covid-kiosk",
              ":alert: {0} {1} at kiosk {2}".format(m.member,txt,url)
              )
  except BaseException as e:
    logger.error("Kiosk mask check error {0}".format(e))
    cv_status=-1
    cv_error="Image Processing Error"
  try:
        url=""
        if imagecode:
            url="https://auth.makeitlabs.com"+url_for("logs.kioskentry",ke=imagecode)
        send_slack_message(
          "#monitoring-security",
          "{2} {0} at entry kiosk {1} {3}".format(m.member,data['event'],icon,url)
          )
  except BaseException as e:
    logger.error("Error slack log {0}".format(e))
  return json_dump({'result':'success','cv_status':cv_status,'cv_error':cv_error}), 200, {'Access-Control-Allow-Origin':'*','Content-type': 'application/json'}

# REQUIRE json payload with proper JSON content-type as such:
# curl http://testkey:testkey@127.0.0.1:5000/api/v1/authorize -H "Content-Type:application/json" -d '{"slack_id":"brad.goodman","resources":[4],"members":[11,22,32],"level":2}'
# This is a hyper-prorected API call, because it cal assume the identity of anyone it specifies
@blueprint.route('/v1/authorize', methods=['POST'])
@api_only
@localhost_only
def api_v1_authorize():
  data=request.get_json()
  if not data:
		return json_dump({'result':'failure','reason':'Not JSON request'}), 400, {'Content-type': 'application/json'}
  if 'slack_id' not in data:
		return json_dump({'result':'failure','reason':'Slack user not specified'}), 400, {'Content-type': 'application/json'}
  user = data['slack_id']
  
  admin = Member.query.filter(Member.slack == user).all()
  if not admin or len(admin)==0:
		return json_dump({'result':'failure','reason':'Slack user unknown'}), 400, {'Content-type': 'application/json'}

  if len(admin)>1:
		return json_dump({'result':'failure','reason':'Multiple slack admin ids found'}), 400, {'Content-type': 'application/json'}

  
  for rid in data['resources']:
    r = Resource.query.filter(Resource.id==rid).one()
    au = AccessByMember.query.filter(AccessByMember.member_id==admin[0].id).filter(AccessByMember.resource_id == rid).one_or_none()

    adminlevel = AccessByMember.LEVEL_NOACCESS
    if admin[0].privs('HeadRM'): adminlevel = AccessByMember.LEVEL_HEADRM
    elif au: adminlevel = au.level
    else: adminlevel= AccessByMember.LEVEL_NOACCESS
  
    if adminlevel < AccessByMember.LEVEL_TRAINER:
      return json_dump({'result':'failure','reason':'%s has insufficient privs for %s'%(admin[0].member,r.name)}), 400, {'Content-type': 'application/json'}

    newlevel = data['level']
    newlevelText = accessLevelToString(newlevel)
    if newlevel  <= AccessByMember.LEVEL_USER: newlevelText=None
    if newlevel>=adminlevel:
      return json_dump({'result':'failure','reason':'%s has insufficient privs to grant level %s on %s'%(admin[0].member,newlevel,r.name)}), 400, {'Content-type': 'application/json'}

  for mid in data['members']:
    oldlevel=AccessByMember.LEVEL_NOACCESS
    m = Member.query.filter(Member.id==mid).one()
    ac = AccessByMember.query.filter(AccessByMember.member_id==mid).filter(AccessByMember.resource_id == rid).one_or_none()
    if ac: oldlevel=ac.level

    # We have the old level, the (requested) new level, and the admin's priv level -
    # Lets see if this is an escalation or deescallation, and if we have privileges to do so

    if (oldlevel >= adminlevel):
      return json_dump({'result':'failure','reason':'%s already has greater privileges on %s than %s can authorize." '%(m.member,r.name,admin[0].member)}), 400, {'Content-type': 'application/json'}

    if ac and newlevel>AccessByMember.LEVEL_NOACCESS: 
      # Just change the level
      ac.level=newlevel
      authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,resource_id=rid,message=newlevelText,member_id=m.id,doneby=admin[0].id,commit=0)
    elif ac and newlevel == AccessByMember.LEVEL_NOACCESS:
      # Delete it
      db.session.delete(ac)
      authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_REVOKED.id,resource_id=rid,member_id=m.id,doneby=admin[0].id,commit=0)
    else:
      # Create new access record
      authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,resource_id=rid,member_id=m.id,message=newlevelText,doneby=admin[0].id,commit=0)
      ac = AccessByMember(member_id = m.id,resource_id = r.id,level=newlevel)
      db.session.add(ac)
    
  db.session.commit()
  authutil.kick_backend()
  return json_dump({'result':'success'}), 200, {'Content-type': 'application/json'}

@blueprint.route('/v1/mac/<string:mac>/config', methods=['GET'])
@api_only
def api_v1_macconfig(mac):
		n = Node.query.filter(Node.mac == mac).one_or_none()
		result = {'status':'success'}
		if not n:
			result['status']='error'
			result['message']='Node not found'
			return json_dump(result, 200, {'Content-type': 'text/plain'})
		return api_v1_nodeconfig(n.name)
	

@blueprint.route('/v3/test', methods=['GET'])
@login_required
def api_v3_test():
		return("Hello world")

# NOTE this requires LOGIN (not API) access because it
# is used by javascript to dynamically find members
@blueprint.route('/v1/members', methods=['GET'])
@login_required
def api_v1_members():
		"""(API) Return a list of all members. either in CSV or JSON"""
		sqlstr = "select m.member,m.plan,m.updated_date,s.expires_date from members m inner join subscriptions s on lower(s.name)=lower(m.stripe_name) and s.email=m.alt_email"
		outformat = request.args.get('output','json')
		filters = {}
		filters['active'] = safestr(request.args.get('active',''))
		filters['access_enabled'] = safestr(request.args.get('enabled',''))
		filters['expired'] = safestr(request.args.get('expired',''))
		filters['plan'] = safestr(request.args.get('plan',''))
		fstring = ""
		if len(filters) > 0:
				fstrings = []
				for f in filters:
						if f == 'active' or f == 'access_enabled':
								if filters[f] == "true" or filters[f] == "false":
										fstrings.append("%s='%s'" % (f,filters[f]))
						if f == 'expired':
								if filters[f] == 'true':
										fstrings.append("p.expires_date < Datetime('now')")
								if filters[f] == 'false':
										fstrings.append("p.expires_date >= Datetime('now')")
						if f == 'plan':
								if filters[f] in ('pro','hobbyist'):
										fstrings.append("m.plan='%s'" % filters[f])
				if len(fstrings) > 0:
						fstring = ' AND '.join(fstrings)
						sqlstr = sqlstr + " where " + fstring
		members = query_db(sqlstr)
		output = ""
		jsonarr = []
		for m in members:
				if outformat == 'csv':
						output = output + "%s,%s,%s,%s\n" % (m['member'],m['plan'],m['updated_date'],m['expires_date'])
				elif outformat == 'json':
						jsonarr.append({'member':m['member'],'plan':m['plan'], 'updated_date': m['updated_date'], 'expires_date': m['expires_date']})
		if outformat == 'csv':
				ctype = "text/plain; charset=utf-8"
		elif outformat == 'json':
				ctype = "application/json"
				output = json_dump(jsonarr)
		return output, 200, {'Content-Type': '%s' % ctype, 'Content-Language': 'en'}

@blueprint.route('/v1/members/<string:id>', methods=['GET'])
@api_only
def api_v1_showmember(id):
  """(API) Return details about a member, currently JSON only"""
  mid = safestr(id)
  #outformat = request.args.get('output','json')
  outformat = 'json'
  m = Member.query.filter(Member.member==mid).one_or_none()
  if not m:
    return "Does not exist", 404, {'Content-type': 'application/json'}
  output = {'member': m.member,
    'plan': m.plan,
    'alt_email': m.plan,
    'firstname': m.firstname,
    'lastname': m.lastname,
    'phone': m.phone}
  return json_dump(output), 200, {'Content-type': 'application/json'}

@blueprint.route('/v1/memberprivs/<string:id>', methods=['GET'])
@api_only
def api_v1_memberprivs(id):
    output=[]
    m = Member.query.filter(Member.id==id)
    m = m.add_column(Resource.name)
    m = m.add_column(AccessByMember.level)
    m = m.join(AccessByMember,AccessByMember.member_id == Member.id)
    m = m.join(Resource,AccessByMember.resource_id == Resource.id)
    for x in  m.all():
      output.append({'resource':x[1],'level':accessLevelToString(x[2])})
    return json_dump(output), 200, {'Content-type': 'application/json'}


@blueprint.route('/v1/resources', methods=['GET'])
@api_only
def api_v1_get_resources():
  result=[]
  resources=Resource.query.all()
  for x in resources:
    result.append({'id':x.id,'name':x.name,'short':x.short,'slack_admin_chan':x.slack_admin_chan,'slack_chan':x.slack_chan})
  return json_dump(result), 200, {'Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/v1/resources/<string:id>/fob/<int:fob>', methods=['OPTIONS'])
#@api_only
def api_v1_show_resource_fob_options(id,fob):
		return "", 200, {
                        'Access-Control-Allow-Origin':'https://plachenko.github.io',
                        'Access-Control-Allow-Headers':'Content-Type,Authorization',
                        'Access-Control-Allow-Credentials':'true',
                        'Access-Control-Allow-Methods':'OPTIONS,GET',
                        'Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/v1/resources/<string:id>/fob/<int:fob>', methods=['GET'])
@api_only
def api_v1_show_resource_fob(id,fob):
		"""(API) Return a list of all tags, their associazted users, and whether they are allowed at this resource"""
		rid = safestr(id)
		# Note: Returns all so resource can know who tried to access it and failed, w/o further lookup
		output = accesslib.getAccessControlList(rid)
    for x in json.loads(output):
      if int(x['raw_tag_id']) == fob:
        #w = Logs.query.order_by(Logs.time_reported.desc()).limit(1).one_or_none()
        m = Member.query.filter(Member.member == x['member']).one_or_none()
        if m:
            t = Logs.query.filter((Logs.member_id == m.id) & (Logs.event_type  == eventtypes.RATTBE_LOGEVENT_MEMBER_KIOSK_ACCEPTED.id))
            t = t.order_by(Logs.time_reported.desc()).limit(1)
            t = t.one_or_none()
            if t: 
                x['lastkiosk']=str(t.time_reported)
        return json.dumps(x), 200, {'Access-Control-Allow-Origin':'*','Content-Type': 'application/json', 'Content-Language': 'en'}
		return "{\"status\":\"Fob not found\"}", 404, {'Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/v1/resources/<string:id>/acl', methods=['OPTIONS'])
#@api_only
def api_v1_show_resource_acl_options(id):
		return "", 200, {
                        'Access-Control-Allow-Origin':'https://plachenko.github.io',
                        'Access-Control-Allow-Headers':'Content-Type,Authorization',
                        'Access-Control-Allow-Credentials':'true',
                        'Access-Control-Allow-Methods':'OPTIONS,GET',
                        'Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/v1/resources/<string:id>/acl', methods=['GET'])
@api_only
def api_v1_show_resource_acl(id):
		"""(API) Return a list of all tags, their associazted users, and whether they are allowed at this resource"""
		rid = safestr(id)
		# Note: Returns all so resource can know who tried to access it and failed, w/o further lookup
		output = accesslib.getAccessControlList(rid)
		return output, 200, {'Access-Control-Allow-Origin':'*','Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/v1/resources/<string:id>/endorsementAcl/<string:endorsement>', methods=['GET'])
@api_only
def api_v1_show_resource_endorsement_acl(id,endorsement):
		"""(API) Return a list of all tags, their associazted users, and whether they are allowed at this resource"""
		rid = safestr(id)
		# Note: Returns all so resource can know who tried to access it and failed, w/o further lookup
		orig = json.loads(accesslib.getAccessControlList(rid))
    output = []
    for x in orig:
      if 'endorsements' in x:
        e = x['endorsements'].strip().split()
        if endorsement in e:
          output.append(x)
    
    output = json.dumps(output,indent=2)
		return output, 200, {'Access-Control-Allow-Origin':'*','Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/ubersearch/<string:ss>',methods=['GET'])
@login_required
def ubersearch_handler(ss):
  output  = json_dump(ubersearch(ss),indent=2)
  return output, 200, {'Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/v0/resources/<string:id>/acl', methods=['GET'])
@api_only
def api_v0_show_resource_acl(id):
		"""(API) Return a list of all tags, their associated users, and whether they are allowed at this resource"""
		rid = safestr(id)
		# Note: Returns all so resource can know who tried to access it and failed, w/o further lookup
		#users = _getResourceUsers(rid)
		users = json_load(accesslib.getAccessControlList(rid))
		outformat = request.args.get('output','csv')
		if outformat == 'csv':
				outstr = "username,key,value,allowed,hashedCard,lastAccessed"
				for u in users:
						outstr += "\n%s,%s,%s,%s,%s,%s" % (u['member'],'0',u['level'],"allowed" if u['allowed'] == "allowed" else "denied",u['tagid'],'2011-06-21T05:12:25')
				return outstr, 200, {'Content-Type': 'text/plain', 'Content-Language': 'en'}

@blueprint.route('/v0/resources/<string:id>/endorsementAcl/<string:endorsement>', methods=['GET'])
@api_only
def api_v0_show_resource_endorsement_acl(id,endorsement):
		"""(API) Return a list of all tags, their associated users, and whether they are allowed at this resource"""
		rid = safestr(id)
		# Note: Returns all so resource can know who tried to access it and failed, w/o further lookup
		#users = _getResourceUsers(rid)
		users = json_load(accesslib.getAccessControlList(rid))
		outformat = request.args.get('output','csv')
		if outformat == 'csv':
				outstr = "username,key,value,allowed,hashedCard,lastAccessed"
				for u in users:
          if 'endorsements' in u:
            e = u['endorsements'].strip().split()
            if endorsement in e:
              outstr += "\n%s,%s,%s,%s,%s,%s" % (u['member'],'0',u['level'],"allowed" if u['allowed'] == "allowed" else "denied",u['tagid'],'2011-06-21T05:12:25')
				return outstr, 200, {'Content-Type': 'text/plain', 'Content-Language': 'en'}

@blueprint.route('/v1/payments/update', methods=['GET'])
@api_only
def api_v1_payments_update():
  """(API) Local host-only API for forcing payment data updates via cron. Not ideal, but avoiding other schedulers"""
  # Simplistic, and not incredibly secure, host-only filter
  host_addr = str.split(request.environ['HTTP_HOST'],':')
  isTest=False
  if current_app.config['globalConfig'].DeployType.lower() != "production":
    isTest=True
    logger.error("Non-Production environment - NOT creating google/slack accounts")
  if request.environ['REMOTE_ADDR'] == host_addr[0]:
    pay.updatePaymentData()
    membership.syncWithSubscriptions(isTest)
    return "Completed."
  else:
    return "API not available to %s expecting %s" % (request.environ['REMOTE_ADDR'], host_addr[0])

@blueprint.route('/v1/test', methods=['GET'])
@api_only
def api_test():
		host_addr = str.split(request.environ['HTTP_HOST'],':')
		str1 = pprint.pformat(request.environ,depth=5)
		if request.environ['REMOTE_ADDR'] == host_addr[0]:
				return "Yay, right host"
		else:
				return "Boo, wrong host"

@blueprint.route('/v1/healthcheck', methods=['GET'])
@api_only
def api_healthcheck():
    status = "ok"
    try:
      health = subprocess.check_output(['uptime'])
    except BaseException as e:
      status = "alert"
      health = "Uptime failed: "+str(e)
    status = {
      'status':status,
      'version':current_app.jinja_env.globals['VERSION'],
      'health':health
    }
    return json_dump(status, 200, {'Content-type': 'application/json'})

def error_401():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'What the hell. .\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

@blueprint.route('/cron/nightly', methods=['GET'])
@api_only
def api_cron_nightly():
  logger.info("Nightly CRON started")
  payments.setupPaymentSystems()
  payments.updatePaymentData()
  isTest=False
  if current_app.config['globalConfig'].DeployType.lower() != "production":
    isTest=True
    logger.error("Non-Production environment - NOT creating google/slack accounts")
  if (membership.syncWithSubscriptions(isTest)  ):
    logger.info("Nightly CRON member sync failed")
    return json_dump({'status':'error','reason':'Member sync failed'}, 200, {'Content-type': 'text/plain'})
  cli_waivers([])
  connect_waivers()
  try:
    automatch_missing_slack_ids()
  except:
    logger.info("Error in nightly slack sync")
  authutil.kick_backend()
  logger.info("Nightly CRON finished")
  return json_dump({'status':'ok'}, 200, {'Content-type': 'text/plain'})

@blueprint.route('/cron/weekly_notices', methods=['GET'])
@api_only
def api_cron_weekly_notices():
  err = send_all_notices()
  if err:
    logger.warning("Weekly notice CRON ERROR")
    return json_dump({'status':'error'}, 401, {'Content-type': 'text/plain'})
  else:
    logger.info("Weekly notice CRON finished")
    return json_dump({'status':'ok'}, 200, {'Content-type': 'text/plain'})

# Meant for CRON job
@blueprint.route('/v1/autoplot/pay', methods=['GET'])
@api_only
def api_autoplot_pay():
  return autoplot_api()

@blueprint.route('/v1/last_tool_event', methods=['GET'])
@api_only
def api_toollog():
  evts = eventtypes.get_events()
  findevents = (
    eventtypes.RATTBE_LOGEVENT_TOOL_ACTIVE.id,
    eventtypes.RATTBE_LOGEVENT_TOOL_INACTIVE.id,
    eventtypes.RATTBE_LOGEVENT_TOOL_LOCKOUT_LOCKED.id,
    eventtypes.RATTBE_LOGEVENT_TOOL_LOCKOUT_UNLOCKED.id,
    eventtypes.RATTBE_LOGEVENT_TOOL_POWERON.id,
    eventtypes.RATTBE_LOGEVENT_TOOL_POWEROFF.id,
    eventtypes.RATTBE_LOGEVENT_TOOL_LOGIN_COMBO.id,
    eventtypes.RATTBE_LOGEVENT_TOOL_LOGIN.id,
    eventtypes.RATTBE_LOGEVENT_TOOL_LOGOUT.id)
  result={}
  t = Logs.query.filter(Logs.tool_id is not None)
  t = Logs.query.filter(Logs.event_type .in_(findevents))
  t = t.order_by(Logs.time_reported.desc())
  t = t.group_by(Logs.tool_id)
  tools = t.all()

  users = []
  for x in tools:
    users.append(x.member_id)

  names={}
  nicknames={}
  for tn in Tool.query.all():
    names[tn.id] = tn.name
    if tn.displayname:
      nicknames[tn.id] = tn.displayname

  members={}
  for m in Member.query.filter(Member.id.in_(users)).all():
    if m.nickname:
      members[m.id] = m.nickname+" "+m.lastname
    else:
      members[m.id] = m.firstname+" "+m.lastname

  for t in tools:
    result[t.tool_id] = {
       'tool_id':t.tool_id,
       'time_reported':t.time_reported.strftime("%Y-%m-%d %H:%M:%S"), 
       'event_code':t.event_type, 
       'event_text':evts[t.event_type] if t.event_type in evts else '', 
       'tool_name': names[t.tool_id] if t.tool_id in names else '', 
       'member_name':members[t.member_id] if t.member_id in members else ''
     }
    if t.tool_id in nicknames:
       result[t.tool_id]['tool_nickname'] = nicknames[t.tool_id]
    else:
       result[t.tool_id]['tool_name']
  return json_dump(result,200, {'Content-type': 'text/plain'},indent=2)

#####
##
##  CLI handlers for API access
##
#####

def cli_addapikey(cmd,**kwargs):
  print "CMD IS",cmd
  apikey = ApiKey(username=cmd[1],name=cmd[2])
  if (len(cmd) >=4):
    apikey.password=cmd[3]
  else:
    apikey.password = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    print "API Key is",apikey.password
  apikey.password = current_app.user_manager.hash_password( apikey.password)
  db.session.add(apikey)
  db.session.commit()
  logger.info("Added API key "+str(cmd[1]))

def cli_deleteapikey(cmd,**kwargs):
  apikey = ApiKey.query.filter(ApiKey.name == cmd[1]).one()
  db.session.delete(apikey)
  db.session.commit()
  logger.info("API key deleted"+str(cmd[1]))

def cli_changeapikey(cmd,**kwargs):
  apikey = ApiKey.query.filter(ApiKey.name == cmd[1]).one()
  apikey.password = current_app.user_manager.hash_password( cmd[2])
  db.session.commit()
  logger.info("Change API key password"+str(cmd[1]))

def cli_listapikeys(cmd,**kwargs):
  apikey = ApiKey.query.all()
  for x in apikey:
      print "Name:",x.name,"Username:",x.username

# Placeholder to test stuff
def cli_querytest(cmd,**kwargs):
	door = Resource.query.filter(Resource.name=="frontdoor").one()
	doorid = door.id
	memberquery = Member.query
	if len(cmd) >= 2:
		memberquery = Member.query.filter(Member.member.ilike("%"+cmd[1]+"%"))
	for member in memberquery.all():
		#acc= accesslib.access_query(doorid,member_id=member.id,tags=False).one_or_none()
		acc= accesslib.access_query(doorid,member_id=member.id,tags=False).first()
		if acc: 
			acc=accesslib.accessQueryToDict(acc)
			(warning,allowed)=accesslib.determineAccess(acc,"DENIED",door)
			print member.member,allowed,warning
		else:
			print member.member,"NODOORACCESS"


# Placeholder to test stuff
def cli_cron(cmd,**kwargs):
  api_cron_nightly()

def register_pages(app):
	app.register_blueprint(blueprint)

# Like: curl 'http://test:test@127.0.0.1:5000/api/v1/setaccess/user@makeitlabs.com?resource=fake-resource-users&slack=CID1234'
@blueprint.route('/v1/setaccess/<string:email>', methods = ['GET'])
@api_only
def member_api_setaccess(email):
	resource = request.args.get('resource','')
	slack = request.args.get('slack','')
	result = {'status':'success'}

	m = Member.query.filter(Member.email.ilike(email))
	m = m.join(Resource,(AccessByMember.resource_id == Resource.id) & (Resource.name == resource))
	m = m.join(AccessByMember,AccessByMember.member_id == Member.id)
	m = m.add_column(AccessByMember.level)
	m = m.one_or_none()

  if m:
    # Record already exists
    if m.level < 0:
      result = {'status':'error',"description":"User already prohibited from using resource"}
    else:
      result = {'status':'success',"description":"User was already authorized"}
  else:
    m = Member.query.filter(Member.email.ilike(email)).one_or_none()
    r = Resource.query.filter(Resource.name == resource).one_or_none()
    if not m:
      result = {'status':'error',"description":"Email not found"}
    elif not r:
      result = {'status':'error',"description":"Resource not found"}
    else:
      ac = AccessByMember(member_id = m.id,resource_id = r.id,level=0)
      db.session.add(ac)
      authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,resource_id=r.id,message="Self-Auth",member_id=m.id,commit=0)
        
      db.session.commit()
      authutil.kick_backend()
      if m.slack and slack != "":
        add_user_to_channel(slack,m.slack)
  
	return json_dump(result, 200, {'Content-type': 'application/json', 'Content-Language': 'en'},indent=2)

# Query like: http://test:test@127.0.0.1:5000/api/v1/getaccess/myemail@makeitlabs.com?resource=resource-users
@blueprint.route("/v1/getaccess/<string:email>", methods = ['GET'])
@api_only
def member_api_getaccess(email):
	resource = request.args.get('resource','')
  #print "FIND ",email,resource
	m = Member.query.filter(Member.email.ilike(email))
	m = m.join(Resource,(AccessByMember.resource_id == Resource.id) & (Resource.name == resource))
	m = m.join(AccessByMember,AccessByMember.member_id == Member.id)
	m = m.add_column(AccessByMember.level)
	m = m.one_or_none()
  if not m:
    result = {'status':'error','description':'Not Found'}
  else:
    #print m
    result = {'status':'success','level':m[1]}
	return json_dump(result, 200, {'Content-type': 'application/json', 'Content-Language': 'en'},indent=2)
