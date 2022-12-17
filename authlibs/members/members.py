# vim:shiftwidth=2:noexpandtab

from ..templateCommon import  *

from authlibs.comments import comments
import datetime
import binascii, zlib
from ..api import api 
from .. import accesslib 
from .. import ago 
from authlibs.members.notices import get_notices,sendnotices
from authlibs.slackutils import add_user_to_channel
import stripe    

## TODO make sure member's w/o Useredit can't see other users' data or search for them
## TODO make sure users can't see cleartext RFID fobs

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

# TODO BKG FIX - Change "memb" to "members" once we've depricated the old handlers
blueprint = Blueprint("members", __name__, template_folder='templates', static_folder="static",url_prefix="/member")

# --------------------------------------
# Member viewing and editing functions
# Routes
#  /members : Show (HTTP GET - members()), Create new (HTTP POST - member_add())
#  /<memberid> - Show (HTTP GET - member_show()), Create new (HTTP POST - member_add())
#  /<memberid>/access - Show current access and interface to change (GET), Change access (POST)
#  /<memberid>/tags - Show tags associated with user (GET), Change tags (POST)
#  /<memberid>/edit - Show current user base info and interface to adjust (GET), Change existing user (POST)
# --------------------------------------


# Strip, but return None if empty
def stripNone(x):
	x = x.strip()
	if x == "":
		return None
	return x

@blueprint.route('/', methods = ['GET'])
@login_required
def members():
        members = {}
        if not current_user.privs('Useredit') and not accesslib.user_is_authorizor(member=current_user,level=AccessByMember.LEVEL_ARM):
            return redirect(url_for('members.member_show',id=current_user.member))
        return render_template('members.html',rec=members,page="all")

@blueprint.route('/', methods= ['POST'])
@login_required
@roles_required(['Admin','Finance','Useredit'])
def member_add():
    """Controller method for POST requests to add a user"""
                        
    member = {}
    mandatory_fields = ['firstname','lastname','memberid','plan','payment']
    optional_fields = ['alt_email','phone','dob','nickname']
    for f in mandatory_fields:
        member[f] = ''
        if f in request.form:
            member[f] = request.form[f]
        if member[f] == '':
            flash("Error: One or more mandatory fields not filled out",'warning')
            return redirect(url_for('members'))
    for f in optional_fields:
        member[f] = ''
        if f in request.form:
            member[f] = request.form[f]
    result = _createMember(member)
    flash(result['message'])
    if result['status'] == "success":
        return redirect(url_for('members.member_show',id=member['memberid']))
    else:
        return redirect(url_for('members.members'))

# TempAuth
@blueprint.route('/<string:id>/tempauth/<string:rid>', methods = ['GET','POST'])
@login_required
def tempauth(id,rid):
  member = Member.query.filter(Member.id == int(id)).one_or_none()
  resource = Resource.query.filter(Resource.id == int(rid)).one_or_none()
  tempauth = TempAuth.query.filter((TempAuth.member_id == int(id)) & (TempAuth.resource_id == int(rid))).all()
  #print "TEMPAUTH",int(id),int(rid),tempauth

  if not member:
    flash("Invalid member","warning")
    return redirect(url_for('members.members'))
  if not resource:
    flash("Invalid resource","warning")
    return redirect(url_for('members.members'))

  if (accesslib.user_privs_on_resource(member=current_user,resource=resource) < AccessByMember.LEVEL_ARM):
    flash("No privileges to grant temp auth on {0}".format(resource.name))
    return redirect(url_for('members.members'))

  if len(tempauth) > 1:
    # We should never have more than one record!
    for x in tempauth[1:-1]:
      db.session.delete(x)
    db.session.commit()

  rec = {
    'times':1,
    'expires':2
  }

  if len(tempauth) >=1:
    if tempauth[0].expires < datetime.datetime.now():
      db.session.delete(tempauth[0])
      db.session.commit()
      tempauth = None
    else:
      rec['times'] = tempauth[0].timesallowed
      rec['expires'] = round((tempauth[0].expires - datetime.datetime.now()).total_seconds() / 3600,1)


  debug = request.method

  if request.method == "POST":
    debug += str (request.form)
    rec['times'] = int(request.form['times'])
    rec['expires'] = float(request.form['hours'])
    if 'SaveChanges' in request.form:
      r = "{0} hours {1} times".format(rec['expires'],rec['times'])
      if tempauth:
        db.session.delete(tempauth[0])
      t = TempAuth(member_id=member.id,resource_id=resource.id,admin_id=current_user.id)
      t.expires = datetime.datetime.now() + datetime.timedelta(hours=rec['times'])
      t.timesallowed = rec['times']
      db.session.add(t)
      authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_TEMP_ACCESS_GRANTED.id,resource_id=resource.id,message=r,member_id=member.id,doneby=current_user.id,commit=0)
      db.session.commit()
      flash("Temporary Authorizaiton Set")
      pass
    elif 'RemoveAuth' in request.form:
      if tempauth:
        db.session.delete(tempauth[0])
        db.session.commit()
        flash("Temporary Authorizaiton Removed")
      pass
    return redirect(url_for('members.member_editaccess',id=member.id))


  return render_template('tempauth.html',debug=debug,rec=rec,member=member,resource=resource,admin=current_user)

# memberedit
@blueprint.route('/<string:id>/edit', methods = ['GET','POST'])
@login_required
@roles_required(['Admin','Finance','Useredit'])
def member_edit(id):
    mid = authutil._safestr(id)
    member = {}

    if request.method=="POST" and (not current_user.privs('Useredit')):
         flash("You cannot edit users",'warning')
         return redirect(url_for('members.members'))

    if request.method=="POST" and 'Unlink' in  request.form:
        s = Subscription.query.filter(Subscription.membership==request.form['membership']).one()
        if s.member_id:
          authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_PAYMENT_UNLINKED.id,member_id=s.member_id,doneby=current_user.id,commit=0)
        s.member_id = None
        db.session.commit()
        btn = '''<form method="POST">
                <input type="hidden" name="member_id" value="%s" />
                <input type="hidden" name="membership" value="%s" />
                <input type="submit" value="Undo" name="Undo" />
                </form>''' % (request.form['member_id'],request.form['membership'])
        flash(Markup("Unlinked. %s" % btn))
    elif 'Undo' in request.form:
        # Relink cleared member ID
        s = Subscription.query.filter(Subscription.membership == request.form['membership']).one()
        s.member_id = request.form['member_id']
        db.session.commit()
        flash ("Undone.")
    elif request.method=="POST" and 'DeleteMember' in  request.form:
        if current_user.privs("Finance"):
          flash (Markup("WARNING: Slack and GMail accounts have <b>not</b> been deleted"),"danger")
          authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_RECORD_DELETED.id,member_id=mid,doneby=current_user.id,commit=0)
          m=Member.query.filter(Member.id==mid).one()
          for s in Subscription.query.filter(Subscription.member_id == m.id).all():
            s.member_id=None
          db.session.delete(m)
          db.session.commit()
          return redirect(url_for("members.members"))
        else:
          flash ("You do not have authority to delete users","warning")
    elif request.method=="POST" and 'SaveChanges' in  request.form:
        nocommit=False
        m=Member.query.filter(Member.id==mid).one()
        f=request.form
        m.member= f['input_member']
        m.firstname= f['input_firstname']
        m.lastname= f['input_lastname']
        m.nickname= f['input_nickname']
        #TODO REMOVE MISSING FIELD CHEKCS HERE
        if 'input_plan' in f: m.plan= f['input_plan']
        if 'input_payment' in f: m.payment= f['input_payment']
        if f['input_phone'] == "None" or f['input_phone'].strip() == "":
            m.phone=None
        else:
          m.phone= f['input_phone']
        if f['input_dob'] == "None" or f['input_dob'].strip() == "":
            m.dob=None
        else:
          if re.match('^\d\d\/\d\d/\d\d\d\d$',f['input_dob']):
            dt = datetime.datetime.strptime(f['input_dob'],"%m/%d/%Y")
            m.dob= dt
          elif re.match('^\d\d\d\d-\d\d-\d\d\s+\d+:\d+:\d+',f['input_dob']):
            dt = datetime.datetime.strptime(f['input_dob'],"%Y-%m-%d %H:%M:%S")
            m.dob= dt
          else:
            flash("Invalid Date of Birth Format - must be \"MM/DD/YYYY\"","danger")
            nocommit=True
        m.slack= f['input_slack'].strip()
        m.memberFolder= stripNone(f['input_memberFolder'])
        m.alt_email= f['input_alt_email'].strip()
        m.email= f['input_email'].strip()
        if 'input_access_enabled' in f:
          if m.access_enabled != 1:
            authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_ACCESS_ENABLED.id,message=f['input_access_reason'],member_id=m.id,doneby=current_user.id,commit=0)
          m.access_enabled=1
          m.access_reason= None
        else:
          if m.access_enabled != 0:
            authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_ACCESS_DISABLED.id,member_id=m.id,doneby=current_user.id,commit=0)
          m.access_enabled=0
          m.access_reason= f['input_access_reason']
        if not nocommit:
          flash("Changes Saved (Please Review/Verify)","success")
          db.session.commit()
          authutil.kick_backend()
        
    #(member,subscription)=Member.query.outerjoin(Subscription).filter(Member.member==mid).first()
    member=db.session.query(Member,Subscription)
    member = member.outerjoin(Subscription).outerjoin(Waiver).filter(Member.id==mid)
    r = member.one_or_none()
    if not r:
        flash("Member not found",'warning')
        return redirect(url_for("members.members"))

    (member,subscription) = r

    # TODO this access display doesn't work at all
    access=db.session.query(Resource).add_column(AccessByMember.level).outerjoin(AccessByMember).outerjoin(Member)
    access = access.filter(Member.member == mid)
    access = access.filter(AccessByMember.active == 1)
    access = access.all()
    acc =[]
    for a in access:
        (r,level) = a
        acc.append({'description':r.name,'level':authutil.accessLevelString(level,user="",noaccess="")})

    if current_user.privs('Useredit'):
        cc=comments.get_comments(member_id=member.id)
    else:
        cc={}
    return render_template('member_edit.html',rec=member,subscription=subscription,access=acc,comments=cc,page="edit")


@blueprint.route('/<string:id>', methods = ['GET'])
@login_required
def member_show(id):
   """Controller method to Display or modify a single user"""
   #TODO: Move member query functions to membership module
   meta = {}
   access = {}
   mid = authutil._safestr(id)
   member=db.session.query(Member,Subscription)
   member = member.join(Subscription).outerjoin(Waiver).filter(Member.member==mid)
   res = member.one_or_none()

   if (not current_user.privs('Useredit')) and res[0].member != current_user.member:
       if current_user.is_arm():
         return redirect(url_for('members.member_editaccess',id=res[0].id))
       flash("You cannot view that user",'warning')
       return redirect(url_for('members.members'))
 
   (warning,allowed,dooraccess)=(None,None,None)
 
   if res:
     (member,subscription) = res

     utc = dateutil.tz.gettz('UTC')
     eastern = dateutil.tz.gettz('US/Eastern')
     if subscription:
       meta['sub_updated_local']=subscription.updated_date.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None).strftime("%a, %b %d, %Y %I:%M %p (Local)")
       meta['sub_created_local']=subscription.created_date.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None).strftime("%a, %b %d, %Y %I:%M %p (Local)")
       meta['sub_expires_local']=subscription.expires_date.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None).strftime("%a, %b %d, %Y %I:%M %p (Local)")

     (warning,allowed,dooraccess)=getDoorAccess(member.id)
     access=db.session.query(Resource).outerjoin(AccessByMember).outerjoin(Member)
     access = access.filter(Member.id == member.id)
     access = access.filter(AccessByMember.active == 1)
     access = access.all()

     if current_user.privs('Useredit'):
         cc=comments.get_comments(member_id=member.id)
     else:
         cc={}

     waivers = Waiver.query.filter(Waiver.member_id == member.id)
     waivers = Waiver.addWaiverTypeCol(waivers)
     waivers = waivers.all()

     for waiver in waivers:
       if (waiver.Waiver.waivertype == Waiver.WAIVER_TYPE_MEMBER):
         meta['waiver']=waiver.Waiver.created_date

     if subscription:
       if subscription.expires_date < datetime.datetime.now():
         meta['is_expired'] = True
       if subscription.active:
         meta['is_inactive'] = True

      
     groupmembers=[]
     bal = member.balance
     if bal is None: bal=0
     vendingBalance="${0:1.2f}".format(float(bal)/100.0)
     if subscription:
       groupmembers=Subscription.query.filter(Subscription.subid == subscription.subid).filter(Subscription.id != subscription.id)
       groupmembers=groupmembers.join(Member,Member.id == Subscription.member_id)
       groupmembers=groupmembers.add_column(Member.member)
       groupmembers=groupmembers.add_column(Member.firstname)
       groupmembers=groupmembers.add_column(Member.lastname)
       groupmembers=groupmembers.all()


     tags = MemberTag.query.filter(MemberTag.member_id == member.id).all()
     return render_template('member_show.html',rec=member,access=access,subscription=subscription,comments=cc,dooraccess=dooraccess,access_warning=warning,access_allowed=allowed,meta=meta,page="view",tags=tags,groupmembers=groupmembers,waivers=waivers,vendingBalance=vendingBalance)
   else:
    flash("Member not found",'warning')
    return redirect(url_for("members.members"))

# See what rights the user has on the given resource
# User and resource User and Resource class objects
def getAccessLevel(user,resource):
		pass

@blueprint.route('/<string:id>/waiver', methods = ['GET','POST'])
@roles_required(['Admin','Finance','Useredit'])
@login_required
def link_waiver(id):
  mid = safestr(id)
  member = db.session.query(Member).filter(Member.id == mid).one_or_none()
  if not member:
    flash("Invalid Member","danger")
    return redirect(url_for('members.members'))
  if 'LinkWaiver' in request.form:
    w = Waiver.query.filter(Waiver.id == request.form['waiverid']).one()
    w.member_id = member.id
    authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_WAIVER_LINKED.id,doneby=current_user.id,member_id=member.id,commit=0)
    if member.access_enabled == 0:
      if ((member.access_reason is None) or (member.access_reason == "")):
        member.access_enabled=1
        authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_ACCESS_ENABLED.id,message="Waiver accepted",member_id=member.id,doneby=current_user.id,commit=0)
      else:
        flash("Access still disabled - had been disabled because: "+str(member.access_reason),"danger")
    db.session.commit()
    flash("Linked waiver","success")
    return redirect(url_for('members.member_show',id=member.member))
  else:
    waivers=Waiver.query.order_by(Waiver.id.desc())
    waivers = Waiver.addWaiverTypeCol(waivers)
    waivers = waivers.outerjoin(Member).add_column(Member.member.label("memb"))
    """
    if 'showall' not in request.values:
      waivers = waivers.limit(50)
    """
    waivers = waivers.all()
    return render_template('link_waiver.html',rec=member,waivers=waivers)

@blueprint.route('/<string:id>/access', methods = ['GET'])
@login_required
def member_editaccess(id):
    """Controller method to display gather current access details for a member and display the editing interface"""
    mid = safestr(id)
    member = db.session.query(Member).filter(Member.id == mid).one_or_none()
    if not member:
      flash("Member","danger")
      return redirect(url_for('members.members'))
    tags = MemberTag.query.filter(MemberTag.member_id == member.id).all()

    q = db.session.query(Resource).outerjoin(AccessByMember,((AccessByMember.resource_id == Resource.id) & (AccessByMember.member_id == member.id)))
    q = q.add_columns(AccessByMember.active,AccessByMember.level,AccessByMember.lockout_reason,AccessByMember.permissions)

    roles=[]
    for r in db.session.query(Role.name).outerjoin(UserRoles,((UserRoles.role_id==Role.id) & (UserRoles.member_id == member.id))).add_column(UserRoles.id).all():
        roles.append({'name':r[0],'id':r[1]})


    # Put all the records together for renderer
    access = []
    for (r,active,level,lockout_reason,permissions) in q.all():
        (myPerms,levelTxt)=authutil.getResourcePrivs(resource=r)
        if not active: 
            level=0
        else:
            try:
                level=int(level)
            except:
                level=0
        levelText=AccessByMember.ACCESS_LEVEL[level]
        if level ==0:
            levelText=""
        permflags=[]
        if r.permissions:
          for p in r.permissions.strip().split():
            haspriv = False
            pending = False
            #print ("CHCINING ",p,"IN",permissions)
            if permissions and p.lower() in permissions.strip().lower().split(): haspriv=True
            if permissions and ("pending_"+p).lower() in permissions.strip().lower().split(): pending=True
            permflags.append({'name':p,'haspriv':haspriv,'pending':pending})
        access.append({'resource':r,'active':active,'level':level,'myPerms':myPerms,'levelText':levelText,'lockout_reason':lockout_reason,'permflags':permflags})
    allowsave=False
    if (current_user.privs('Useredit')): allowsave=True
    elif (accesslib.user_is_authorizor(current_user)): allowsave=True

    tempauths={}
    for ta in TempAuth.query.filter(TempAuth.member_id == member.id).all():
      #print "EVA",ta,(ta.expires > datetime.datetime.now())
      if ((ta.expires > datetime.datetime.now()) and (ta.timesallowed > 0)):
        tempauths[ta.resource_id]=True
    #print "TEMPAUTHS",tempauths
    return render_template('member_access.html',tempauths=tempauths,rec=member,access=access,tags=tags,roles=roles,page="access",allowsave=allowsave)


@blueprint.route('/<string:id>/access', methods = ['POST'])
@login_required
def member_setaccess(id):
    """Controller method to receive POST and update user access"""
    mid = safestr(id)
    access = {}
    # Find all the items. If they were changed, and we are allowed
    # to change them - make it so in DB
    member = Member.query.filter(Member.id == mid).one()
    if ((member.id == current_user.id) and not (current_user.privs('Admin'))):
        flash("You can't change your own access",'warning')
        return redirect(url_for('members.member_editaccess',id=mid))
    if ('revoke_local_login' in request.form) and request.form['revoke_local_login']=='on':
        member.password=None
        flash("Local GUI Access Revoked")
      
    if (('password1' in request.form and 'password2' in request.form) and
        (request.form['password1'] != "") and 
        current_user.privs('Admin')):
            if request.form['password1'] == request.form['password2']:
                member.password=current_app.user_manager.hash_password(request.form['password1'])
                flash("Password Changed")
            else:
                flash("Password Mismatch")

    if 'lockout_op' in request.form:
      rid = request.form['lockout_resource_id']
      reason = request.form['lockout_reason']
      (myPerms,alstr) = authutil.getResourcePrivs(resourceid=rid)
      acl = AccessByMember.query.filter(AccessByMember.member_id == mid,AccessByMember.resource_id==rid).one()
      if myPerms <= acl.level:
        flash("Insufficient privileges to change that user's access on that resource","warning")
        return redirect(url_for('members.member_editaccess',id=mid))

      if  request.form['lockout_op'] == "Lock":
        if reason.strip() == "":
          flash("Must specify a reason for lockout","warning")
        else:
          acl.lockout_reason=reason
          authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_RESOURCE_LOCKOUT.id,resource_id=rid,member_id=member.id,doneby=current_user.id,commit=0)
          db.session.commit()
          flash("Access suspended","success")
          authutil.kick_backend()
          return redirect(url_for('members.member_editaccess',id=mid))
      elif  request.form['lockout_op'] == "Unlock":
        acl.lockout_reason=None
        authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_RESOURCE_UNLOCKED.id,resource_id=rid,member_id=member.id,doneby=current_user.id,commit=0)
        db.session.commit()
        flash("Access restored","success")
        authutil.kick_backend()
        return redirect(url_for('members.member_editaccess',id=mid))

    for key in request.form:
        if key.startswith("orgrole_") and current_user.privs('Admin'):
            r = key.replace("orgrole_","")
            oldval=request.form["orgrole_"+r] == "on"
            newval="role_"+r in request.form

            if oldval and not newval:
                rr = UserRoles.query.filter(UserRoles.member_id == member.id).filter(UserRoles.role_id == db.session.query(Role.id).filter(Role.name == r)).one_or_none()
                if rr: 
                    db.session.delete(rr)
                    authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_PRIVILEGE_REVOKED.id,message=r,member_id=member.id,doneby=current_user.id,commit=0)
                    flash("Removed %s privs" % r)
            elif newval and not oldval:
                rr = UserRoles(member_id = member.id,role_id = db.session.query(Role.id).filter(Role.name == r))
                authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_PRIVILEGE_GRANTED.id,message=r,member_id=member.id,doneby=current_user.id,commit=0)
                flash("Added %s privs" % r)
                db.session.add(rr)


        if key.startswith("orgaccess_"):
            oldcheck = request.form[key]=='on'
            r = key.replace("orgaccess_","")
            resource = Resource.query.filter(Resource.name==r).one()
            (myPerms,alstr) = authutil.getResourcePrivs(resource=resource)
            if "privs_"+r in request.form:
                p = int(request.form['privs_'+r])
            else:
                p = 0

            try:
                alstr = AccessByMember.ACCESS_LEVEL[p]
            except:
                alstr = "???"

            newcheck=False
            if "access_"+r in request.form:
                newcheck=True

            # TODO do we have privs to do this?? (Check levels too)
            # TODO Don't allow someone to "demote" someone of higher privledge
            if myPerms >= 1:
                # Find existing privs or not
                # There are THREE levels of privileges at play here:
                # acc.level - The OLD level for this record
                # p - the NEW level we are trying to change to
                # myPerm - The permissions level of the user making this change

                # Find existing record
                acc = AccessByMember.query.filter(AccessByMember.member_id == member.id)
                acc = acc.filter(resource.id == AccessByMember.resource_id)
                acc = acc.one_or_none()

                # This sections creates a record, if needed.
                if acc is None and newcheck == False:
                    # Was off - and no change - Do nothing
                    continue
                elif acc is None and newcheck == True:
                    # Was off - but we turned it on - Create new one
                    db.session.add(Logs(member_id=member.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,doneby=current_user.id))
                    acc = AccessByMember(member_id=member.id,resource_id=resource.id)
                    db.session.add(acc)
                    if (resource.slack_chan):
                      add_user_to_channel(resource.slack_chan,member)
                elif acc and newcheck == False and p>=myPerms:
                    flash("You aren't authorized to disable %s privs on %s" % (alstr,r),'warning')

                # This section deals with setting role permissions on the record
                if acc.level == p:
                    pass # No change
                elif (p>=myPerms):
                    flash("You aren't authorized to grant %s privs on %s" % (alstr,r),'warning')
                elif (acc.level >= myPerms):
                    flash("You aren't authorized to demote %s privs on %s" % (alstr,r),'warning')
                elif acc.level != p:
                    db.session.add(Logs(member_id=member.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_PRIV_CHANGE.id,message=alstr,doneby=current_user.id))
                    acc.level=p

                # This section sets permission flags to whatever's present
                permission_flags=[]
                if acc.permissions: permission_flags=acc.permissions.strip().split()
                for pf in request.form:
                  if pf.startswith("permflag_"+r+"_"):
                    pff = pf.replace("permflag_"+r+"_","")
                    if "pending_"+pff in permission_flags: permission_flags.remove("pending_"+pff)
                    if "origpermflag_"+r+"_"+pff not in request.form or request.form["origpermflag_"+r+"_"+pff] == "off":
                      aastr = "Added endorsement: "+pff
                      permission_flags.append(pff)
                      db.session.add(Logs(member_id=member.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_PRIV_CHANGE.id,message=aastr,doneby=current_user.id))

                # Log revoked permission flags
                for pf in request.form:
                  if pf.startswith("origpermflag_"+r+"_"):
                    pff = pf.replace("origpermflag_"+r+"_","")
                    if "permflag_"+r+"_"+pff not in request.form:
                      if request.form[pf] == 'on':
                        aastr = "Removed endorsement: "+pff
                        while pff in permission_flags: permission_flags.remove(pff)
                        db.session.add(Logs(member_id=member.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_PRIV_CHANGE.id,message=aastr,doneby=current_user.id))

                acc.permissions=" ".join(permission_flags)

                if acc and newcheck == False and acc.level < myPerms:
                    #delete
                    db.session.add(Logs(member_id=mid,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_REVOKED.id,doneby=current_user.id))
                    db.session.delete(acc)


    db.session.commit()
    flash("Member access updated")
    authutil.kick_backend()
    return redirect(url_for('members.member_editaccess',id=mid))

@blueprint.route('/<string:id>/tags', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance','Useredit'])
def member_tags(id):
    """Controller method to gather and display tags associated with a memberid"""
    mid = safestr(id)
    #sqlstr = "select tag_ident,tag_type,tag_name from tags_by_member where member = '%s'" % mid
    #tags = query_db(sqlstr)
    tags = MemberTag.query.filter(MemberTag.member_id==mid).all()
    member=Member.query.filter(Member.id==mid).one_or_none()
    if not member:
      flash("Invalid Tag","danger")
      return redirect(url_for('members.members'))
    return render_template('member_tags.html',mid=mid,tags=tags,rec=member,page="tags")

@blueprint.route('/updatebackends', methods = ['GET'])
@login_required
def update_backends():
    authutil.kick_backend()
    flash("Backend Update Request Sent")
    return redirect(url_for('index'))

def add_member_tag(mid,ntag,tag_type,tag_name):
    """Associate a tag with a Member, given a known safe set of values"""
    etag = MemberTag.query.filter(MemberTag.tag_type == tag_type).filter(MemberTag.tag_ident == ntag).one_or_none()

    if not etag:
        tag = MemberTag(tag_ident = ntag,tag_name=tag_name,tag_type=tag_type,member_id=mid)
        db.session.add(tag)
        db.session.add(Logs(member_id=mid,event_type=eventtypes.RATTBE_LOGEVENT_MEMBER_TAG_ASSIGN.id,doneby=current_user.id,message=tag.longhash))
        db.session.commit()
        return True
    else:
        return False

@blueprint.route('/unassociate', methods = ['POST'])
@login_required
@roles_required(['Admin','Finance'])
def unassociate():
    mid = request.form['memberid']
    mem=Member.query.filter(Member.id==mid).one()
    mem.membership=None
    sub=Subscription.query.filter(Subscription.member_id==mid).one()
    authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_PAYMENT_UNLINKED.id,member_id=mid,doneby=current_user.id,commit=0)
    sub.member_id=None
    db.session.commit()
    flash ("Subscription unassociated","success")
    return redirect(url_for('members.member_show',id=mem.member))

@blueprint.route('/<string:id>/tags', methods = ['POST'])
@login_required
@roles_required(['Admin','Finance','Useredit'])
def member_tagadd(id):
    """(Controller) method for POST to add tag for a user, making sure they are not duplicates"""
    mid = safestr(id)
    ntag = safestr(request.form['newtag'])
    ntagtype = safestr(request.form['newtagtype'])
    ntagname = safestr(request.form['newtagname'])
    ntag = authutil.rfid_validate(ntag)
    if ntag is None:
        flash("ERROR: The specified RFID tag is invalid, must be 10-digit all-numeric",'danger')
    else:
        if add_member_tag(mid,ntag,ntagtype,ntagname):
            authutil.kick_backend()
            flash("Tag added.",'success')
        else:
            flash("Error: That tag is already associated with a user",'danger')
    return redirect(url_for('members.member_tags',id=mid))

@blueprint.route('/tags/delete/<string:tag_ident>', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance','Useredit'])
def member_tagdelete(tag_ident):
    """(Controller) Delete a Tag from a Member (HTTP GET, for use from a href link)"""
    t = MemberTag.query.filter(MemberTag.id == tag_ident).join(Member,Member.id == MemberTag.member_id).one_or_none()
    if not t:
        flash("Tag not found",'warning')
        return redirect(url_for('index'))
    mid = t.member_id
    db.session.add(Logs(member_id=mid,event_type=eventtypes.RATTBE_LOGEVENT_MEMBER_TAG_UNASSIGN.id,doneby=current_user.id,message=t.longhash))
    db.session.delete(t)
    db.session.commit()
    authutil.kick_backend()
    flash("Tag deleted","success")
    return redirect(url_for("members.member_tagadd",id=mid))

@blueprint.route('/tags/enable/<string:tag_ident>', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance','Useredit'])
def member_tagenable(tag_ident):
    """(Controller) Enable a Tag from a Member (HTTP GET, for use from a href link)"""
    t = MemberTag.query.filter(MemberTag.id == tag_ident).join(Member,Member.id == MemberTag.member_id).one_or_none()
    if not t:
        flash("Tag not found",'warning')
        return redirect(url_for('index'))
    mid = t.member_id
    if not t.tag_type.startswith("inactive-"):
      flash("Tag was already enabled","warning")
    else:
      t.tag_type = t.tag_type.replace("inactive-","")
      db.session.commit()
      authutil.kick_backend()
      flash("Tag Enabled","success")
    return redirect(url_for("members.member_tagadd",id=mid))

@blueprint.route('/tags/disable/<string:tag_ident>', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance','Useredit'])
def member_tagdisable(tag_ident):
    t = MemberTag.query.filter(MemberTag.id == tag_ident).join(Member,Member.id == MemberTag.member_id).one_or_none()
    if not t:
      flash("Tag not found",'warning')
      return redirect(url_for('index'))
    mid = t.member_id
    if t.tag_type.startswith("inactive-"):
      flash("Tag was already disabled","warning")
    else:
      t.tag_type = "inactive-"+t.tag_type
      db.session.commit()
      authutil.kick_backend()
      flash("Tag Disabled","success")
    return redirect(url_for("members.member_tagadd",id=mid))

def generate_member_report(members):
  fields=[ 'member', "email", "alt_email", "firstname", "lastname", "phone","dob",
          "plan", "slack_id","access_enabled", "access_reason", "active", "rate_plan", "sub_active",'memberWaiver','guestWaiver','prostoreWaiver','workspaceWaiver']
  s=""
  for f in fields:
    s += "\""+str(f)+"\","
  yield s+"\n"

  for m in members:
    s = ""
    values = (m.Member.member,m.Member.email, m.Member.alt_email, m.Member.firstname, m.Member.lastname,
      m.Member.phone, m.Member.dob, m.Member.plan, m.Member.slack, m.Member.access_enabled, m.Member.access_reason,
      m.Member.active)
    if m.Subscription:
      values += (m.Subscription.rate_plan, m.Subscription.active)
    else:
      values += ("","")
    values += (m.memberWaivers,m.guestWaivers,m.prostoreWaivers,m.workspaceWaivers)
    for f in values:
        s += "\""+str(f)+"\","
    yield s+"\n"

@blueprint.route('/member_report')
@login_required
@roles_required(['Admin','Finance','Useredit'])
def member_report():
    members=db.session.query(Member,Subscription)
    members = members.join(Subscription,isouter=True)
    sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("waiverCount")).group_by(Waiver.member_id)
    sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_MEMBER)
    sq = sq.subquery()
    members = members.add_column(sq.c.waiverCount.label("memberWaivers")).outerjoin(sq,(sq.c.member_id == Member.id))

    sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("guestWaiverCount")).group_by(Waiver.member_id)
    sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_NONMEMBER)
    sq = sq.subquery()
    members = members.add_column(sq.c.guestWaiverCount.label("guestWaivers")).outerjoin(sq,(sq.c.member_id == Member.id))

    sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("prostoreWaiverCount")).group_by(Waiver.member_id)
    sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)
    sq = sq.subquery()
    members = members.add_column(sq.c.prostoreWaiverCount.label("prostoreWaivers")).outerjoin(sq,(sq.c.member_id == Member.id))

    sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("workspaceWaiverCount")).group_by(Waiver.member_id)
    sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_WORKSPACE)
    sq = sq.subquery()
    members = members.add_column(sq.c.workspaceWaiverCount.label("workspaceWaivers")).outerjoin(sq,(sq.c.member_id == Member.id))
    members = members.all()
    meta={}

    if 'download' in request.values:
      resp=Response(generate_member_report(members),mimetype='text/csv')
      resp.headers['Content-Disposition']='attachment; filename=members.csv'
      return resp
    else:
      return render_template('member_report.html',members=members,meta=meta)

@blueprint.route('/member_report_api')
@api.api_only
def member_report_api():
    members=db.session.query(Member,Subscription)
    members = members.join(Subscription,isouter=True)
    sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("waiverCount")).group_by(Waiver.member_id)
    sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_MEMBER)
    sq = sq.subquery()
    members = members.add_column(sq.c.waiverCount.label("memberWaivers")).outerjoin(sq,(sq.c.member_id == Member.id))

    sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("guestWaiverCount")).group_by(Waiver.member_id)
    sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_NONMEMBER)
    sq = sq.subquery()
    members = members.add_column(sq.c.guestWaiverCount.label("guestWaivers")).outerjoin(sq,(sq.c.member_id == Member.id))

    sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("prostoreWaiverCount")).group_by(Waiver.member_id)
    sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)
    sq = sq.subquery()
    members = members.add_column(sq.c.prostoreWaiverCount.label("prostoreWaivers")).outerjoin(sq,(sq.c.member_id == Member.id))

    sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("workspaceWaiverCount")).group_by(Waiver.member_id)
    sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_WORKSPACE)
    sq = sq.subquery()
    members = members.add_column(sq.c.workspaceWaiverCount.label("workspaceWaivers")).outerjoin(sq,(sq.c.member_id == Member.id))
    members = members.all()
    meta={}

    resp=Response(generate_member_report(members),mimetype='text/csv')
    resp.headers['Content-Disposition']='attachment; filename=members.csv'
    return resp

@blueprint.route('/tags/lookup', methods = ['GET','POST'])
@login_required
@roles_required(['Admin','Finance','Useredit'])
def lookup_tag():
    tags=[]
    if 'input_tag' in request.form:
        tag=request.form['input_tag'].strip()

        if re.match("^\d{10}$",tag):
            ts =  MemberTag.query.filter(MemberTag.tag_ident==tag).join(Member,Member.id == MemberTag.member_id).add_column(Member.id).add_column(Member.member).all()
            if len(ts)==0:
                flash("No matching tag found",'warning')
                ts = [[MemberTag(tag_ident=tag),'','']]
            else:
                flash("Matched",'success');
            for t in ts:
                tags.append({'member_id':t[1],'member':t[2],'tag':t[0]})
        elif re.match("^[0-9,a-f]{56}$",tag):
            for x in MemberTag.query.all():
                if x.longhash == tag:
                    m = Member.query.filter(Member.id == x.member_id).one()
                    tags.append({'member_id':m.id,'member':m.member,'tag':x})
            if len(tags) ==0:
                flash("No matching hash found",'warning')
        elif re.match("^[0-9,a-f]{4}\.\.\.[0-9,a-f]{4}$",tag):
            for x in MemberTag.query.all():
                if x.shorthash == tag:
                    m = Member.query.filter(Member.id == x.member_id).one()
                    tags.append({'member_id':m.id,'member':m.member,'tag':x})
            if len(tags) ==0:
                flash("No matching fingerprint found",'warning')

        else:
            flash("Unknown Fob Type","danger")
    return render_template("lookup_tag.html",tags=tags)
#----------
#
# Brad's test stuff
#
#------------

@blueprint.route('/revokeadmin', methods=['GET'])
@login_required
def revokeadmin():
    if current_user.member in ("Adam.Shrey","Brad.Goodman","Bradley.Goodman","Steve.Richardson","Bill.Schongar"):
      r = UserRoles.query.filter(UserRoles.member_id == current_user.id)
      r = r.join(Role,(UserRoles.role_id == Role.id) & (Role.name == "Admin"))
      r = r.one_or_none()
      if r is None:
        flash ("You are not admin","warning")
      else:
        db.session.delete(r)
        db.session.commit()
        flash ("Admin revoked")

    return redirect(url_for('index'))

@blueprint.route('/grantadmin', methods=['GET'])
@login_required
def grantadmin():
    if current_user.member in ("Adam.Shrey","Brad.Goodman","Bradley.Goodman","Steve.Richardson","Bill.Schongar"):
      r = UserRoles.query.filter(UserRoles.member_id == current_user.id)
      r = r.join(Role,(UserRoles.role_id == Role.id) & (Role.name == "Admin"))
      r = r.one_or_none()
      if r is not None:
        flash ("You are already admin","warning")
      else:
        flash ("Admin granted")
        r = UserRoles()
        r.member_id=current_user.id
        r.role_id=Role.query.filter(Role.name=="Admin").one().id
        db.session.add(r)
        db.session.commit()
    return redirect(url_for('index'))

@blueprint.route('/<string:id>/payment', methods=['GET','POST'])
@roles_required(['Admin','Finance'])
def payment_update(id):
  x = Member.query.filter(Member.id==id).one()
  s = Subscription.query.filter(Subscription.member_id == x.id).one_or_none()
  #print ("FORM DATA IS",request.form)
  stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
  customer=[]
  if s:
    output=None
    try:
      customer = stripe.Customer.retrieve(s.customerid)
    except:
      pass
    #print (output)
  if 'stripeToken' in request.form:
    # This was a callback from Stripe CC update form - update CC
    cc = request.form['stripeToken']
    try:
      ## stripe.Customer.update(card=cc) ## BE CAREFULL!!!
      pass
      flash("Stripe Card Updated","success")
    except BaseException as e:
      flash("Stripe Card Update failed: "+str(e),"warning")
    return (redirect(url_for("members.payment_update",id=id)))
  return (render_template("update_payment.html",rec=x,customer=customer))

@blueprint.route('/test', methods=['GET'])
def bkgtest():
    names=['frontdoor','woodshop','laser']
    result={}
    for n in names:
        #result[n]=getResourcePrivs(Resource.query.filter(Resource.name==n).one())
        result[n]=getResourcePrivs(resourcename=n)
    return json_dump(result,indent=2), 200, {'Content-type': 'application/json'}

@blueprint.route('/member_notices', methods=['GET','POST'])
@login_required
@roles_required(['Admin',"Useredit"])
def notices():
  errs=0
  if 'send_notices' in request.form:
    #print ("REQUET FORM")
    for x in request.form:
      if x.startswith("notify_send_"):
        member_id = x.replace("notify_send_","")
        member = Member.query.filter(Member.id == member_id).one()
        notice = {
          'id':member.id,
          'member':member.member,
          'firstname':member.firstname,
          'lastname':member.lastname,
          'alt_email':member.alt_email,
          'email':member.email,
          'notices':request.form[x].split("|")
        }
        #print (x,notice['member'],notice['notices'])
        #authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_NOTICE_SENT.id,member_id=member_id,message=request.form[x].replace("|"," "),doneby=current_user.id,commit=0)
        errs+=sendnotices(notice)

    if errs:
      flash("%s errors sending notices" % errs,"warning")
        
    db.session.commit()
    return redirect(url_for("members.notices"))
  memberNotices = get_notices()
  eastern = dateutil.tz.gettz('US/Eastern')
  utc = dateutil.tz.gettz('UTC')
  now=datetime.datetime.now()
  for m in memberNotices:
    if memberNotices[m]['lastNoticeWhen']:
      dt=memberNotices[m]['lastNoticeWhen'].replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)
      (memberNotices[m]['when'],memberNotices[m]['ago'],other)=ago.ago(dt,now)
  return (render_template("member_notices.html",notices=memberNotices))

@blueprint.route('/admin_roles', methods=['GET'])
@login_required
@roles_required('Admin')
def admin_page():
    roles=Role.query.all()
    admins =Member.query.join(UserRoles,UserRoles.member_id == Member.id).join(Role,Role.id == UserRoles.role_id)
    admins = admins.add_column(Role.name).group_by(Member.member).all()
    roles=[]
    for x in admins:
        roles.append({'member':x[0],'role':x[1]})

    privs=AccessByMember.query.filter(AccessByMember.level>0).join(Member,Member.id==AccessByMember.member_id)
    privs = privs.join(Resource,Resource.id == AccessByMember.resource_id)
    privs = privs.add_columns(Resource.name,AccessByMember.level,Member.member,Member.id)
    privs = privs.all()
    p=[]
    for x in privs:
        p.append({'member_id':x[4],'member':x[3],'resource':x[1],'priv':AccessByMember.ACCESS_LEVEL[int(x[2])]})

    return render_template('admin_page.html',privs=p,roles=roles)

def _createMember(m):
    """Add a member entry to the database"""
    sqlstr = "Select member from members where member = '%s'" % m['memberid']
    members = query_db(sqlstr)
    if members:
        return {'status': 'error','message':'That User ID already exists'}
    else:
        sqlstr = """insert into members (member,firstname,lastname,phone,dob,plan,nickname,access_enabled,active)
                    VALUES ('%s','%s','%s','%s','','%s',0,0)
                 """ % (m['memberid'],m['firstname'],m['lastname'],m['phone'],m['dob'],m['nickname'])
        execute_db(sqlstr)
        get_db().commit()
    return {'status':'success','message':'Member %s was created' % m['memberid']}
    authutil.kick_backend()

def getDoorAccess(id):
  r = db.session.query(Resource.id).filter(Resource.name == "frontdoor").one_or_none()
  if r:
    acc = accesslib.access_query(r.id,member_id=id,tags=False)
    acc = acc.first()
    if  not acc:
       msg = "No Access Record (Needs orientation?)"
       if current_app.config['globalConfig'].Config.has_option('General','LockoutMessage'):
         msg = current_app.config['globalConfig'].Config.get('General','LockoutMessage')
       return (msg,False,None)
  acc=accesslib.accessQueryToDict(acc)

  (warning,allowed) = accesslib.determineAccess(acc,"Door access pending orientation")
  return (warning,allowed.lower()=='allowed',acc)

def register_pages(app):
  app.register_blueprint(blueprint)
