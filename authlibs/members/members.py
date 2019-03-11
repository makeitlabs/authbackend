# vim:shiftwidth=2:noexpandtab

from ..templateCommon import  *

from authlibs.comments import comments
import datetime
import binascii, zlib
from ..api import api 
from .. import accesslib 

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

@blueprint.route('/', methods = ['GET'])
@login_required
def members():
	members = {}
        if not current_user.privs('Useredit') and not accesslib.user_is_authorizor(member=current_user,level=AccessByMember.LEVEL_ARM):
            return redirect(url_for('members.member_show',id=current_user.member))
	return render_template('members.html',rec=members,page="all")

@blueprint.route('/', methods= ['POST'])
@login_required
@roles_required(['Admin','Useredit'])
def member_add():
		"""Controller method for POST requests to add a user"""
                        
		member = {}
		mandatory_fields = ['firstname','lastname','memberid','plan','payment']
		optional_fields = ['alt_email','phone','nickname']
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

# memberedit
@blueprint.route('/<string:id>/edit', methods = ['GET','POST'])
@login_required
@roles_required(['Admin','Useredit'])
def member_edit(id):
		mid = authutil._safestr(id)
		member = {}

                if request.method=="POST" and (not current_user.privs('Useredit')):
                     flash("You cannot edit users",'warning')
                     return redirect(url_for('members.members'))

		if request.method=="POST" and 'Unlink' in  request.form:
				s = Subscription.query.filter(Subscription.membership==request.form['membership']).one()
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
					m=Member.query.filter(Member.id==mid).one()
					for s in Subscription.query.filter(Subscription.member_id == m.id).all():
						s.member_id=None
					db.session.delete(m)
					db.session.commit()
					return redirect(url_for("members.members"))
				else:
					flash ("You do not have authority to delete users","warning")
		elif request.method=="POST" and 'SaveChanges' in  request.form:
				flash ("Changes Saved (Please Review!)")
				m=Member.query.filter(Member.id==mid).one()
				f=request.form
				m.member= f['input_member']
				m.firstname= f['input_firstname']
				m.lastname= f['input_lastname']
				#TODO REMOVE MISSING FIELD CHEKCS HERE
				if 'input_plan' in f: m.plan= f['input_plan']
				if 'input_payment' in f: m.payment= f['input_payment']
				if f['input_phone'] == "None" or f['input_phone'].strip() == "":
						m.phone=None
				else:
					m.phone= f['input_phone']
				m.slack= f['input_slack']
				m.alt_email= f['input_alt_email']
				m.email= f['input_email']
				if 'input_access_enabled' in f:
					if m.access_enabled != 1:
						authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_ACCSSS_ENABLED.id,message=f['input_access_reason'],member_id=m.id,doneby=current_user.id,commit=0)
					m.access_enabled=1
					m.access_reason= None
				else:
					if m.access_enabled != 0:
						authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_ACCSSS_DISABLED.id,member_id=m.id,doneby=current_user.id,commit=0)
					m.access_enabled=0
					m.access_reason= f['input_access_reason']
				db.session.commit()
				
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
	 member = member.outerjoin(Subscription).outerjoin(Waiver).filter(Member.member==mid)
	 res = member.one_or_none()

	 if (not current_user.privs('Useredit')) and res[0].member != current_user.member:
			 if current_user.is_arm():
				 return redirect(url_for('members.member_editaccess',id=res[0].id))
			 flash("You cannot view that user",'warning')
			 return redirect(url_for('members.members'))
 
	 (warning,allowed,dooraccess)=(None,None,None)
 
	 if res:
		 (member,subscription) = res
		 (warning,allowed,dooraccess)=getDoorAccess(member.id)
		 access=db.session.query(Resource).outerjoin(AccessByMember).outerjoin(Member)
		 access = access.filter(Member.id == member.id)
		 access = access.filter(AccessByMember.active == 1)
		 access = access.all()

                 if current_user.privs('Useredit'):
                     cc=comments.get_comments(member_id=member.id)
                 else:
                     cc={}
		 waiver = Waiver.query.filter(Waiver.member_id == member.id).first()

		 if waiver:
			 meta['waiver']=waiver.created_date
		 if subscription:
			 if subscription.expires_date < datetime.datetime.now():
				 meta['is_expired'] = True
			 if subscription.active:
				 meta['is_inactive'] = True

		 return render_template('member_show.html',rec=member,access=access,subscription=subscription,comments=cc,dooraccess=dooraccess,access_warning=warning,access_allowed=allowed,meta=meta,page="view")
	 else:
		flash("Member not found",'warning')
		return redirect(url_for("members.members"))

# See what rights the user has on the given resource
# User and resource User and Resource class objects
def getAccessLevel(user,resource):
		pass

@blueprint.route('/<string:id>/access', methods = ['GET'])
@login_required
def member_editaccess(id):
		"""Controller method to display gather current access details for a member and display the editing interface"""
		mid = safestr(id)
		member = db.session.query(Member).filter(Member.id == mid).one_or_none()
		if not member:
			flash("Invalid Tag","danger")
			return redirect(url_for('members.members'))
		tags = MemberTag.query.filter(MemberTag.member_id == member.id).all()

		q = db.session.query(Resource).outerjoin(AccessByMember,((AccessByMember.resource_id == Resource.id) & (AccessByMember.member_id == member.id)))
		q = q.add_columns(AccessByMember.active,AccessByMember.level,AccessByMember.lockout_reason)

		roles=[]
		for r in db.session.query(Role.name).outerjoin(UserRoles,((UserRoles.role_id==Role.id) & (UserRoles.member_id == member.id))).add_column(UserRoles.id).all():
				roles.append({'name':r[0],'id':r[1]})


		# Put all the records together for renderer
		access = []
		for (r,active,level,lockout_reason) in q.all():
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
				access.append({'resource':r,'active':active,'level':level,'myPerms':myPerms,'levelText':levelText,'lockout_reason':lockout_reason})
		allowsave=False
		if (current_user.privs('Useredit')): allowsave=True
		elif (accesslib.user_is_authorizor(current_user)): allowsave=True
		return render_template('member_access.html',rec=member,access=access,tags=tags,roles=roles,page="access",allowsave=allowsave)

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

								if acc is None and newcheck == False:
										# Was off - and no change - Do nothing
										continue
								elif acc is None and newcheck == True:
										# Was off - but we turned it on - Create new one
										db.session.add(Logs(member_id=member.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,doneby=current_user.id))
										acc = AccessByMember(member_id=member.id,resource_id=resource.id)
										db.session.add(acc)
								elif acc and newcheck == False and p>=myPerms:
										flash("You aren't authorized to disable %s privs on %s" % (alstr,r),'warning')

								if (p>=myPerms):
										flash("You aren't authorized to grant %s privs on %s" % (alstr,r),'warning')
								elif (acc.level >= myPerms):
										flash("You aren't authorized to demote %s privs on %s" % (alstr,r),'warning')
								elif acc.level != p:
										db.session.add(Logs(member_id=member.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_PRIV_CHANGE.id,message=alstr,doneby=current_user.id))
										acc.level=p

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
@roles_required(['Admin','Useredit'])
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
		flash("Backend Update Request Send")
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
                flash("Tag deleted","success")
                return redirect(url_for("members.member_tagadd",id=mid))

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

@blueprint.route('/test', methods=['GET'])
def bkgtest():
    names=['frontdoor','woodshop','laser']
    result={}
    for n in names:
        #result[n]=getResourcePrivs(Resource.query.filter(Resource.name==n).one())
        result[n]=getResourcePrivs(resourcename=n)
    return json_dump(result,indent=2), 200, {'Content-type': 'application/json'}

@blueprint.route('/admin', methods=['GET'])
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
        sqlstr = """insert into members (member,firstname,lastname,phone,plan,nickname,access_enabled,active)
                    VALUES ('%s','%s','%s','%s','','%s',0,0)
                 """ % (m['memberid'],m['firstname'],m['lastname'],m['phone'],m['nickname'])
        execute_db(sqlstr)
        get_db().commit()
    return {'status':'success','message':'Member %s was created' % m['memberid']}
    kick_backend()

def getDoorAccess(id):
  r = db.session.query(Resource.id).filter(Resource.name == "frontdoor").one_or_none()
  if r:
    acc = accesslib.access_query(r.id,member_id=id,tags=False)
    acc = acc.first()
    if not acc:
	    return ("No Access Record (Needs orientation?)",False,None)
  acc=accesslib.accessQueryToDict(acc)

  (warning,allowed) = accesslib.determineAccess(acc,"Door access pending orientation")
  return (warning,allowed.lower()=='allowed',acc)

def register_pages(app):
	app.register_blueprint(blueprint)
