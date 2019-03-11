# vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs import accesslib
from sqlalchemy import case
# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

blueprint = Blueprint("authorize", __name__, template_folder='templates', static_folder="static",url_prefix="/authorize")

@blueprint.route('/', methods=['GET','POST'])
@login_required
def authorize():
    # Before anything - see if we have any privs to do any authorization

    if not accesslib.user_is_authorizor(current_user):
      flash("You do not have permissions to authorize people on any resources",'warning')
      return redirect(url_for("index"))
    others={}
    if "authorize" in request.form:
      members=[]
      resources=[]
      i=0
      while "memberid_"+str(i) in request.form:
        temp = request.form['memberid_'+str(i)]
        members.append(temp)
        i+=1
      i=0
      while "resource_"+str(i) in request.form:
        temp = request.form['resource_'+str(i)]
        resources.append(Resource.query.filter(Resource.name == temp).one())
        i+=1
      if len(members) == 0:
        others['error']="No members specified to authorize"
      elif len(resources) == 0:
        others['error']="No resources specified to authorize"
      else:
        error=False
        for m in members:
            for r in resources:
                mem=AccessByMember.query.join(Member,((Member.id==AccessByMember.member_id) & (Member.member==m) & (AccessByMember.resource_id == r.id))).one_or_none()
                if mem:
                    #print "%s already has access to %s." % (m,r.name)
                    flash("%s already has access to %s." % (m,r.name),"warning")
                else:
                    (level,levelText)=authutil.getResourcePrivs(resource=r)
                    if (level <= 0): 
                        #print "You don't have privileges to grant access on %s" 
                        flash("You don't have privileges to grant access on %s" % r,"danger")
                    else:
                        #print "%s granted access to %s" % (m,r.name)
                        flash("%s granted access to %s" % (m,r.name),"success")
                        db.session.add(AccessByMember(member_id=Member.query.filter(Member.member == m).with_entities(Member.id),resource_id=r.id,level=0))

        db.session.commit()
        #others['message']="Authorized "+" ".join(members)+" on "+" ".join([x.name for x in resources])
    if 'search' in request.form and (request.form['search'] != ""):
      searchstr = authutil._safestr(request.form['search'])
      sstr = "%"+searchstr+"%"
      members = Member.query.filter(((Member.member.ilike(searchstr))) | (Member.alt_email.ilike(sstr))).all()
    else:
      members = []

    resources = Resource.query.all()
    res=[]

    for r in resources:
        (level,levelText)=authutil.getResourcePrivs(resource=r)
        res.append({'resource':r,'level':level,'levelText':levelText})

    return render_template("authorize.html",members=members,resources=res,**others)

@blueprint.route("/membersearch/<string:search>",methods=['GET'])
@login_required
def membersearch(search):
  filters=[]
  offset = 0
  limit = 50
  for x in request.values:
      if x.startswith('filter_'): filters.append(x)
  sstr = authutil._safestr(search)
  sstr = "%"+sstr+"%"
  res = db.session.query(Member.member,Member.firstname,Member.lastname,Member.alt_email,Member.id)
  res = res.filter((Member.firstname.ilike(sstr) | Member.lastname.ilike(sstr) | Member.alt_email.ilike(sstr) | Member.member.ilike(sstr)))
  res = res.outerjoin(Subscription,Subscription.member_id == Member.id)
  res = accesslib.addQuickAccessQuery(res)
  res = res.add_column(Subscription.active)
  res = res.add_column(Subscription.expires_date)
			
  if 'offset' in request.values:
      offset = int(request.values['offset'])
  
  res = res.all()
  result=[]
  counted=0
  for x in res:
    if len(filters) > 0:
      if x[5] == "No Subscription" and 'filter_nosub' not in filters: continue
      if x[5] == "Grace Period"  and 'filter_grace' not in filters: continue
      if x[5] == "Access Disabled"  and 'filter_noaccess' not in filters: continue
      if x[5] == "Active"  and 'filter_active' not in filters: continue
      if x[5] == "Expired"  and 'filter_expired' not in filters: continue
      if x[5] == "Recent Expire"  and 'filter_recentexpire' not in filters: continue
    if (offset > 0): 
      offset -= 1
      continue
    if counted >= limit: continue
    result.append({'member':x[0],'firstname':x[1],'lastname':x[2],'email':x[3], 'id':x[4], 'active':x[5]})
    counted += 1
  return json.dumps(result)

def register_pages(app):
	app.register_blueprint(blueprint)
