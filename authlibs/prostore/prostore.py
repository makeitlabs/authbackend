# vim:shiftwidth=2


from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago
from authlibs.accesslib import addQuickAccessQuery
from .notices import sendnotices
from sqlalchemy.sql.expression import label
import urllib

blueprint = Blueprint("prostore", __name__, template_folder='templates', static_folder="static",url_prefix="/prostore")


def get_next_bin_aruco():
  used = set([r[0] for r in db.session.query(ProBin.aruco).filter(ProBin.aruco >= 1, ProBin.aruco <= 499).all() if r[0] is not None])
  for i in range(1, 500):
    if i not in used:
      return i
  return None

def get_next_loc_aruco():
  used = set([r[0] for r in db.session.query(ProLocation.aruco).filter(ProLocation.aruco >= 500, ProLocation.aruco <= 999).all() if r[0] is not None])
  for i in range(500, 1000):
    if i not in used:
      return i
  return None


def log_bin_event(bin,event,commit=0):
  f=[]
  if bin.location_id:
    l = ProLocation.query.filter(ProLocation.id == bin.location_id).one_or_none()
    if l:
      f.append("Loc:%s" % l.location)
  if bin.name:
    f.append("Bin:%s" % bin.name)
  f.append("%s" % ProBin.BinStatuses[int(bin.status)])
  message = " ".join(f)
  authutil.log(event,member_id=bin.member_id,message=message,doneby=current_user.id,commit=commit)

@blueprint.route('/bins', methods=['GET','POST'])
@roles_required(['Admin','RATT','ProStore','Useredit'])
@login_required
def bins():
  if 'create_bin' in request.form:
    b= request.form['input_name']
    
    brec = ProBin()
    if 'input_location' in request.form and request.form['input_location'] != "Unspecified":
      l = request.form['input_location']
      # If it's a "single" location - make sure it's not already in use
      loc = ProLocation.query.filter(ProLocation.location == l).one()
      if loc.loctype == ProLocation.LOCATION_TYPE_SINGLE:
        bincnt = ProBin.query.filter(ProBin.location_id == loc.id).count()
        if bincnt != 0:
          flash("Location is already in-use","danger")
          return redirect(url_for("prostore.bins"))
      brec.location_id = loc.id

    arucono = request.form.get('input_aruco', '').strip()
    if arucono:
        try:
            brec.aruco = int(arucono)
        except:
            pass
    else:
        brec.aruco = get_next_bin_aruco()

    if brec.aruco is not None and brec.aruco != 0 and (brec.aruco < 1 or brec.aruco > 499):
        flash("Grid aruco codes must be 1-499", "danger")
        return redirect(url_for("prostore.bins"))

    if 'member_radio' in request.form:
      m = request.form['member_radio']
      mem = Member.query.filter(Member.member == m).one()
      brec.member_id = mem.id

    if b.strip() != "":
      bin = ProBin.query.filter(ProBin.name == b.strip()).one_or_none()
      if bin:
        flash("Bin name already exists","danger")
        return redirect(url_for("prostore.bins"))

    if b.strip() != "": brec.name=b.strip()
    brec.status = int(request.form['input_status'])
    brec.status_updated_at = datetime.utcnow()
    db.session.add(brec)
    log_bin_event(brec,eventtypes.RATTBE_LOGEVENT_PROSTORE_ASSIGNED.id)
    db.session.commit()
    flash("Bin Added","success")
    return redirect(url_for("prostore.bins"))
    
  bins=ProBin.query  
  bins=bins.outerjoin(ProLocation)
  bins=bins.add_column(ProLocation.location)
  bins=bins.outerjoin(Member)
  bins=bins.add_column(Member.member)

  sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("waiverCount")).group_by(Waiver.member_id)
  sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)
  sq = sq.subquery()
  
  bins = bins.add_column(sq.c.waiverCount.label("waiverCount")).outerjoin(sq,(sq.c.member_id == Member.id))
  bins = bins.outerjoin(Subscription,Subscription.member_id == Member.id)

  bins=addQuickAccessQuery(bins)
  bins=ProBin.addBinStatusStr(bins)
  bins=bins.all()

  locs=db.session.query(ProLocation,func.count(ProBin.id).label("usecount")).outerjoin(ProBin).group_by(ProLocation.id)
  locs=locs.all()
  return render_template('bins.html',bins=bins,bin=None,locations=locs,statuses=enumerate(ProBin.BinStatuses))

@blueprint.route('/print_label/<int:bin_id>', methods=['GET'])
@roles_required(['Admin','ProStore'])
@login_required
def print_label(bin_id):
    try:
        bin = ProBin.query.filter(ProBin.id == bin_id).one_or_none()
        if not bin:
            return (json_dump({"result": "error", "message":"Bin not found"} ,indent=2), 404, {'Content-type': 'application/json', 'Content-Language': 'en'})
            
        if not bin.aruco:
            bin.aruco = get_next_bin_aruco()
            if not bin.aruco:
                return (json_dump({"result": "error", "message":"No available aruco codes"} ,indent=2), 500, {'Content-type': 'application/json', 'Content-Language': 'en'})
            db.session.commit()
            
        member = Member.query.filter(Member.id == bin.member_id).one_or_none()
        member_name = member.member if member else "Unassigned"
        
        data = urllib.parse.urlencode({'number': bin.aruco, 'name': member_name}).encode('utf-8')
        req = urllib.request.Request("http://labelprinter:8080", data=data, method='POST')
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
    except BaseException as e:
        return (json_dump({"result": "error", "message":str(e)} ,indent=2), 500, {'Content-type': 'application/json', 'Content-Language': 'en'})
    return (json_dump({"result": "ok", "member":member_name, "code": bin.aruco} ,indent=2), 200, {'Content-type': 'application/json', 'Content-Language': 'en'})

@blueprint.route('/print_location_label/<int:loc_id>', methods=['GET'])
@roles_required(['Admin','ProStore'])
@login_required
def print_location_label(loc_id):
    try:
        loc = ProLocation.query.filter(ProLocation.id == loc_id).one_or_none()
        if not loc:
            return (json_dump({"result": "error", "message":"Location not found"} ,indent=2), 404, {'Content-type': 'application/json', 'Content-Language': 'en'})
            
        if not loc.aruco:
            loc.aruco = get_next_loc_aruco()
            if not loc.aruco:
                return (json_dump({"result": "error", "message":"No available aruco codes"} ,indent=2), 500, {'Content-type': 'application/json', 'Content-Language': 'en'})
            db.session.commit()
            
        data = urllib.parse.urlencode({'number': loc.aruco, 'name': loc.location}).encode('utf-8')
        req = urllib.request.Request("http://labelprinter:8080", data=data, method='POST')
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
    except BaseException as e:
        return (json_dump({"result": "error", "message":str(e)} ,indent=2), 500, {'Content-type': 'application/json', 'Content-Language': 'en'})
    return (json_dump({"result": "ok", "location":loc.location, "code": loc.aruco} ,indent=2), 200, {'Content-type': 'application/json', 'Content-Language': 'en'})

@blueprint.route('/bin_add/<string:bin>', methods=['GET'])
@roles_required(['Admin','ProStore'])
@login_required
def bin_add(bin):
  #return render_template('bin.html',bin=b,locations=locs,statuses=enumerate(ProBin.BinStatuses),comments=comments)
  locs=db.session.query(ProLocation,func.count(ProBin.id).label("usecount")).filter(ProLocation.location == bin).outerjoin(ProBin).group_by(ProLocation.id).all()
  newbin = ProBin()
  newbin.name=""
  newbin.aruco=get_next_bin_aruco() or 1
  return render_template('bin_add.html',bin=newbin,locations=locs,statuses=enumerate(ProBin.BinStatuses),forcestatus = 2,selectlocation=bin, ago=ago)
  
@blueprint.route('/bin/<string:id>', methods=['GET','POST'])
@roles_required(['Admin','ProStore'])
@login_required
def bin_edit(id):
  if 'delete_bin' in request.form:
    bin = ProBin.query.filter(ProBin.id == request.form['input_id']).one()
    log_bin_event(bin,eventtypes.RATTBE_LOGEVENT_PROSTORE_UNASSIGNED.id)
    db.session.delete(bin)
    db.session.commit()
    flash("Bin Deleted","success")  
    return redirect(url_for("prostore.bins"))

  if 'save_bin' in request.form:
    # Save
    #print ("BIN_EDIT",request.form)
    bin = ProBin.query.filter(ProBin.id == request.form['input_id']).one()
    if 'member_radio' in request.form:
      bin.member_id=Member.query.filter(Member.member == request.form['member_radio']).one().id
    elif request.form['unassign_member_hidden'] == "yes":
      bin.member_id = None
    if request.form['input_name']:
      bin.name = request.form['input_name']
    else:
      bin.name=None
    new_status = int(request.form['input_status'])
    if bin.status != new_status:
        bin.status = new_status
        bin.status_updated_at = datetime.utcnow()
    bin.location_id = request.form['input_location']
    p= request.form['input_aruco']
    try:
        bin.aruco = int(p)
    except:
        pass
    if (bin.aruco is not None) and (bin.aruco != 0) and ((bin.aruco < 1) or (bin.aruco > 499)):
        flash("Grid aruco codes must be 1-499")
        return redirect(url_for('prostore.grid'))

    log_bin_event(bin,eventtypes.RATTBE_LOGEVENT_PROSTORE_CHANGED.id)
    db.session.commit()
    flash("Updates Saved","success")  
    return redirect(url_for("prostore.bin_edit",id=request.form['input_id']))
      
  b=ProBin.query.filter(ProBin.id==id)
  b=b.add_columns(ProBin.name,ProBin.status)
  b=b.outerjoin(ProLocation)
  b=b.add_column(ProLocation.location)
  b=b.outerjoin(Member)
  b=b.add_column(Member.member)

  b=b.add_column(func.count(Waiver.id).label("waiverDate"))
  b=b.outerjoin(Waiver,((Waiver.member_id == ProBin.member_id) & (Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)))

  b=b.outerjoin(Subscription,Subscription.member_id == Member.id)
  b=addQuickAccessQuery(b)
  b=ProBin.addBinStatusStr(b)
  #print "QUERY",b
  b=b.one()

  if b.ProBin is None:
    flash("Bin does not exist","danger")  
    return redirect(url_for("prostore.locations"))
  try:
      if (b.ProBin.member_id is None):
        sub = None
      else:
        sub = Subscription.query.filter(Subscription.member_id == b.ProBin.member_id).one_or_none()
  except BaseException as e:
    flash("Error getting member subscription","danger")  
    print (f"Member Sugscription error - id {b.ProBin.member_id} - error: {e}\n")
    return redirect(url_for("prostore.locations"))

  iamPro = True if sub is not None and sub.rate_plan in ('pro', 'produo') else False
  locs=db.session.query(ProLocation,func.count(ProBin.id).label("usecount")).outerjoin(ProBin).group_by(ProLocation.id)
  locs=locs.all()
  print ("BIN",b)
  return render_template('bin.html',bin=b,locations=locs,iAmPro=iamPro,statuses=enumerate(ProBin.BinStatuses),comments=comments, ago=ago)

@blueprint.route('/locations', methods=['GET','POST'])
@roles_required(['Admin','ProStore'])
@login_required
def locations():
  if 'delete' in request.values:
    loc = ProLocation.query.filter(ProLocation.location==request.values['delete']).one_or_none()
    if not loc:
      flash("Location not found","warning")
    else:
      flash("Location \"%s\" deleted" % request.values['delete'],"success")
      db.session.delete(loc)
      db.session.commit()
  if 'AddLoc' in request.form and 'addloc_name' in request.form:
    newloc = ProLocation()
    newloc.location=request.form['addloc_name']
    newloc.loctype=request.form['input_loctype']
    db.session.add(newloc)
    db.session.commit()
    flash("Location added","success")
    return redirect(url_for("prostore.locations"))
    
  locs=ProLocation.query.order_by(ProLocation.loctype.desc(),ProLocation.location)
  locs=ProLocation.addLocTypeCol(locs,blankSingle=True).all()
  return render_template('locations.html',locations=locs)

@blueprint.route('/selectchoices', methods=['POST'])
@login_required
def selectChoices():
    ProBinChoice.query.filter(ProBinChoice.member_id == current_user.id).delete()
    for x in request.form:
        if x.startswith('select-'):
            v = x.replace("select-","")
            r = request.form[x]
            loc = ProLocation.query.filter(ProLocation.location == v).one_or_none()

            if r is not None and r.strip() != "":
                c = ProBinChoice()
                c.member_id = current_user.id
                c.location_id = loc.id
                c.rank = r
                db.session.add(c)


    db.session.commit()

    return redirect(url_for("prostore.grid"))

@blueprint.route('/choose', methods=['GET'])
@login_required
def choose():
  bins=ProBin.query  
  bins=bins.outerjoin(ProLocation)
  bins=bins.add_column(ProLocation.location)
  bins=bins.outerjoin(Member)
  bins=bins.add_columns(Member.member,Member.lastname,Member.firstname)
  bins=bins.add_column(Member.id.label("member_id"))
  bins=bins.outerjoin(Waiver,((Waiver.member_id == ProBin.member_id) & (Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)))
  bins=bins.add_column(Waiver.created_date.label("waiverDate"))
  bins = bins.outerjoin(Subscription,Subscription.member_id == Member.id)
  bins=bins.add_columns(Subscription.rate_plan)
  bins=addQuickAccessQuery(bins)
  bins=ProBin.addBinStatusStr(bins).all()
  
  ab={}
  iHaveABin=False
  sub = Subscription.query.filter(Subscription.member_id == current_user.id).one_or_none()
  iamPro = True if sub is not None and sub.rate_plan in ('pro', 'produo') else False

  c = ProBinChoice.query.filter(ProBinChoice.member_id == current_user.id)
  c = c.join(ProLocation,ProLocation.id == ProBinChoice.location_id)
  c = c.add_column(ProLocation.location)
  c = c.add_column(ProBinChoice.rank)

  myranks={}
  for cc in c.all():
      if cc.rank is not None:
          myranks[cc.location] = cc.rank


  for b in bins:
    if b.location:
      ab[b.location] = {
        'binid':b.ProBin.id,
        'status':"In-Use"
      }
    if b.location in myranks:
        ab[b.location]['rank']=myranks[b.location]
    if b.member_id == current_user.id:
      ab[b.location]['style'] = "background-color:#D0FFD0"
      iHaveABin=True

  grids = StorageGrid.query.all()

  if iamPro and not iHaveABin:
      return render_template('choose.html',bins=ab,grids=grids,ranks=myranks)
  else:
      flash ("You already have a bit and therefore cannot choose a new one")
      return redirect(url_for('prostore.grid'))

@blueprint.route('/waitlist', methods=['GET','POST'])
@roles_required(['Admin','ProStore'])
@login_required
def waitlist():
  dstr = ""
  mn = mx = 0
  if request.method == "POST" and 'ChangeDraft' in request.form and request.form['ChangeDraft'] == "View":
      dstr = request.form['draft']
      dd= dstr.strip().split("-")
      try:
          mn = int(dd[0])
          mx = int(dd[1]) if len(dd)==2 else int(dd[0])
      except:
          pass

  if request.method == "POST" and 'Update' in request.form and request.form['Update'] == "Update":
      for x in request.form:
          if x.startswith("choose-"):
              loc = x.replace("choose-","")
              mem =  request.form[x].strip()
              if mem != "":
                  mem = int(request.form[x])
                  pl = ProLocation.query.filter(ProLocation.location == loc).one_or_none()
                  if pl is None:
                      flash(f"Location {loc} not found","danger")
                  else:
                      b = ProBin.query.filter(ProBin.location_id == pl.id).one_or_none()
                      if b is not None:
                          flash(f"Location {loc} already has a bin","danger")
                      else:
                          b = ProBin()
                          b.status = ProBin.BINSTATUS_IN_USE
                          b.member_id = mem
                          b.location_id = pl.id
                          db.session.add(b)
      db.session.commit()


  grids = StorageGrid.query.all()
  bins = ProBin.query
  bins = bins.outerjoin(ProLocation,ProLocation.id == ProBin.location_id)
  bins = bins.add_column(ProBin.member_id)
  bins = bins.add_column(ProLocation.location)
  bins = bins.all()
  ab={}
  members={} # Track members who have bins
  for b in bins:
      if b.location is not None and b.location.strip() != "":
          if b.location not in ab: ab[b.location]={}
          ab[b.location]['status']='In-Use'
          members[b.member_id] = True

  c = ProBinChoice.query
  c = c.join(ProLocation,ProLocation.id == ProBinChoice.location_id)
  c = c.join(Member,Member.id == ProBinChoice.member_id)
  if (mx != 0) and (mn != 0):
      c = c.filter(Member.draft >= mn)
      c = c.filter(Member.draft <= mx)
  c = c.add_column(ProLocation.location)
  c = c.add_column(ProBinChoice.rank)
  c = c.add_column(Member.id)
  c = c.add_column(Member.member)

  for cc in c.all():
        if cc.location not in ab: ab[cc.location]={}
        if 'status' not in ab[cc.location] or ab[cc.location]['status'] != 'In-Use':
            if 'list' not in ab[cc.location]: ab[cc.location]['list']=[]
            if cc.id not in members:
                ab[cc.location]['list'].append({
                      'member':cc.member,
                      'member_id':cc.id,
                      'rank':cc.rank
                      })

  # Sort all of our locations in rank order
  for cc in c.all():
        if cc.location in ab and 'list' in ab[cc.location]: 
            ab[cc.location]['list'] = sorted(ab[cc.location]['list'],key=lambda d: d['rank'])

  # Find bins with an uncontended #1 pick
  for cc in c.all():
        picks=0
        uncontended_mem_id=0
        if cc.location in ab and 'list' in ab[cc.location]: 
            for b in ab[cc.location]['list']:
                if b['rank'] ==1:
                    picks += 1
                    uncontended_mem_id=b['member_id']

        if picks == 1:
            ab[cc.location]['comment'] = "Uncontended";
            ab[cc.location]['uncontended'] = uncontended_mem_id;




  return render_template('waitlist.html',bins=ab,grids=grids,draft=dstr)

@blueprint.route('/grid', methods=['GET','POST'])
@login_required
def grid():
  bins=ProBin.query  
  bins=bins.outerjoin(ProLocation)
  bins=bins.add_column(ProLocation.location)
  bins=bins.outerjoin(Member)
  bins=bins.add_columns(Member.member,Member.lastname,Member.firstname)
  bins=bins.add_column(Member.id.label("member_id"))
  bins=bins.outerjoin(Waiver,((Waiver.member_id == ProBin.member_id) & (Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)))
  bins=bins.add_column(Waiver.created_date.label("waiverDate"))
  bins = bins.outerjoin(Subscription,Subscription.member_id == Member.id)
  bins=bins.add_columns(Subscription.rate_plan)
  bins=addQuickAccessQuery(bins)
  bins=ProBin.addBinStatusStr(bins).all()
  
  ab={}
  iHaveABin=False
  sub = Subscription.query.filter(Subscription.member_id == current_user.id).one_or_none()
  iamPro = True if sub is not None and sub.rate_plan in ('pro', 'produo') else False
  if not iamPro:
      flash ("Storage bins are a \"Pro\"-Level membership perk. Please upgrade your membership to obtain bin privileges")
      return redirect(url_for('index'))

  for b in bins:
    if b.location:
      ab[b.location] = {
        'binid':b.ProBin.id,
      }

      if b.ProBin.name:
        ab[b.location]['binname']=b.ProBin.name
      else:
        ab[b.location]['binname']=""
        
      if b.member:
        ab[b.location]['member']=b.member
        ab[b.location]['firstname']=b.firstname
        ab[b.location]['lastname']=b.lastname
      else:
        ab[b.location]['firstname']=""
        ab[b.location]['lastname']=""

      # Check for dupes
      for bb in bins:
          if bb.location:
            if (b.location != bb.location) and (b.member == bb.member):
              ab[b.location]['style'] = "background-color:#ff4040"

      if (current_user.privs('ProStore','Finance')):
        if not b.waiverDate:
          ab[b.location]['style'] = "background-color:#ffffd0"
        if b.rate_plan not in ('pro', 'produo'):
          ab[b.location]['style'] = "background-color:#ffd49f"
        if b.ProBin.status > 2:
          ab[b.location]['style'] = "background-color:#ffd49f"
        if b.ProBin.status  == 0:
          ab[b.location]['style'] = "background-color:#a3ff9f"
        if b.active != "Active" and b.active != "Grace Period":
          ab[b.location]['style'] = "background-color:#ffd0d0"
        if b.ProBin.status >= 4:
          ab[b.location]['style'] = "background-color:#000000; color:#ffffff"
          ab[b.location]['a_style'] = "color:#ffffff"
      else: 
        if b.member_id == current_user.id:
          ab[b.location]['style'] = "background-color:#D0FFD0"
          iHaveABin=True

  # Regular Pro memember doesn't have a bin - let them find one
  if (not current_user.privs('ProStore','Finance')) and iamPro and not iHaveABin:
      return redirect(url_for('prostore.choose'))

  grids = StorageGrid.query.all()
  locs = {}
  for l in  ProLocation.query.all():
      locs[l.location] = True


  return render_template('grid.html',bins=ab,grids=grids,locs=locs)

def singleBinStatus(bin_id):
  mybin = {}
  bins=ProBin.query
  bins=bins.outerjoin(ProLocation)
  bins=bins.add_column(ProLocation.location)
  bins=bins.outerjoin(Member)
  bins=bins.add_columns(Member.member,Member.lastname,Member.firstname)
  bins=bins.add_column(Member.id.label("member_id"))
  bins=bins.outerjoin(Waiver,((Waiver.member_id == ProBin.member_id) & (Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)))
  bins=bins.add_column(Waiver.created_date.label("waiverDate"))
  bins = bins.outerjoin(Subscription,Subscription.member_id == Member.id)
  bins=bins.add_columns(Subscription.rate_plan)
  bins=addQuickAccessQuery(bins)
  bins=ProBin.addBinStatusStr(bins).all()
  
  ab={}
  iHaveABin=False
  sub = Subscription.query.filter(Subscription.member_id == current_user.id).one_or_none()
  iamPro = True if sub is not None and sub.rate_plan in ('pro', 'produo') else False
  if not iamPro:
      flash ("Storage bins are a \"Pro\"-Level membership perk. Please upgrade your membership to obtain bin privileges")
      return redirect(url_for('index'))

  for b in bins:
    if b.ProBin.id == bin_id:
      mybin = {
        'location':b.location,
        'bin_id':bin_id
      }

      if b.ProBin.name:
        mybin['binname']=b.ProBin.name
      else:
        mybin['binname']=""
        
      if b.member:
        mybin['member']=b.member
        mybin['firstname']=b.firstname
        mybin['lastname']=b.lastname
      else:
        mybin['firstname']=""
        mybin['lastname']=""

      # Check for dupes
      for bb in bins:
          if bb.location:
            if (b.location != bb.location) and (b.member == bb.member):
              mybin['style'] = "background-color:#ff4040"
              mybin['error'] = "Duplicate Bins"

      if (current_user.privs('ProStore','Finance')):
        if not b.waiverDate:
          mybin['style'] = "background-color:#ffffd0"
          mybin['error'] = "No Waiver"
        if b.rate_plan not in ('pro', 'produo'):
          mybin['style'] = "background-color:#ffd49f"
          mybin['error'] = "Non-Pro Member"
        if b.ProBin.status > 2:
          mybin['style'] = "background-color:#ffd49f"
          mybin['error'] = "Bin Status: "+b.binstatusstr
        if b.ProBin.status  == 0:
          mybin['style'] = "background-color:#a3ff9f"
        if b.active != "Active" and b.active != "Grace Period":
          mybin['style'] = "background-color:#ffd0d0"
          mybin['error'] = "Expired Membership"
  return mybin

@blueprint.route('/notices', methods=['GET','POST'])
@roles_required(['Admin','RATT','ProStore','Useredit'])
@login_required
def notices():
  err=0
  debugOnly=False
  if 'debugOnly' in request.form and request.form['debugOnly']:
    debugOnly=True
  if 'send_notices' in request.form:
    debug=[]
    for x in request.form:
      if x.startswith("notify_send_"):
        bid = x.replace("notify_send_","")
        notices = request.form['notify_notices_'+bid]
        (e,d) = sendnotices(bid,notices,debugOnly)
        err +=e
        debug.append(d)
    if err:
      flash("%s errors sending email notices" % err,"danger")
    elif debugOnly:
      flash("Debug only - no messages sent","warning")
      return render_template('testNotices.html',debug=debug)
    else:
      flash("Notices sent","success")
      return render_template('testNotices.html',debug=debug)
    
  bins=ProBin.query.filter(ProBin.member_id != None)
  bins=bins.outerjoin(ProLocation)
  bins=bins.add_column(ProLocation.location)
  bins=bins.outerjoin(Member)
  bins=bins.add_column(Member.member)

  sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("waiverCount")).group_by(Waiver.member_id)
  sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)
  sq = sq.subquery()
  
  bins = bins.add_column(sq.c.waiverCount.label("waiverCount")).outerjoin(sq,(sq.c.member_id == Member.id))
  bins = bins.outerjoin(Subscription,Subscription.member_id == Member.id)
  bins=bins.add_columns(Subscription.rate_plan)
  bins=addQuickAccessQuery(bins)
  bins=ProBin.addBinStatusStr(bins).all()

  result=[]
  for b in bins:
    bb={}
    bb['ProBin'] = b.ProBin
    bb['active'] = b.active
    bb['location'] = b.location
    bb['binstatusstr'] = b.binstatusstr
    bb['member'] = b.member
    bb['waiverCount'] = b.waiverCount

    log =Logs.query.filter(Logs.member_id == b.ProBin.member_id).filter(Logs.event_type == eventtypes.RATTBE_LOGEVENT_PROSTORE_NOTICE_SENT.id)
    log = log.order_by(Logs.time_logged.desc()).first()
    if log:
      bb['lastNoticeWhen'] = log.time_reported
      bb['lastNoticeWhat'] = log.message
    else:
      bb['lastNoticeWhen'] = ""
      bb['lastNoticeWhat'] = ""
    # Which notices are recommented??
    rcmd = []
    if b.waiverCount is None or b.waiverCount <1: rcmd.append("NoWaiver")
    if b.active != "Active": rcmd.append("Subscription")
    if b.rate_plan not in ('pro', 'produo'): rcmd.append("NonPro")

    # Check Dups
    for bbb in bins:
      if b.location and bbb.location:
        pass
        if (b.location != bbb.location) and (b.member == bbb.member):
          rcmd.append("Dup")

    if b.ProBin.status == ProBin.BINSTATUS_GONE:
      rcmd.append("BinGone")
    elif b.ProBin.status == ProBin.BINSTATUS_GRACE_PERIOD:
      rcmd.append("Grace")
    elif b.ProBin.status == ProBin.BINSTATUS_FORFEITED:
      rcmd.append("Forefeit")
    elif b.ProBin.status == ProBin.BINSTATUS_MOVED:
      rcmd.append("Moved")
    elif b.ProBin.status == ProBin.BINSTATUS_DONATED:
      rcmd.append("Donated")
    
    bb['notice']=" ".join(rcmd)
    result.append(bb)

  
  locs=db.session.query(ProLocation,func.count(ProBin.id).label("usecount")).outerjoin(ProBin).group_by(ProLocation.id)
  locs=locs.all()
  return render_template('notices.html',bins=result,bin=None,locations=locs,statuses=enumerate(ProBin.BinStatuses))

  
  
# v0.8 migration
def migrate(cmd,**kwargs):
  for f in ('Garage','Cleanspace'):
    for x in "ABCDEFGH" if f == 'Garage' else "AB":
      for y in range(1,7 if f == 'Garage' else 5):
        name= "%s-%s-%s" % (f,x,y)
        l = ProLocation()
        l.location = name
        l.loctype = 0
        db.session.add(l)
  db.session.commit()

### GRID MANAGEMENT

@blueprint.route('/gridlist', methods=['GET','POST'])
@roles_required(['Admin','ProStore'])
@login_required
def gridlist():
	"""(Controller) Display Grids and controls"""
	now=datetime.now()
	grids = []
	for x in StorageGrid.query.all():
		grids.append({'id':x.id,
			'name':x.name,
			'short':x.short,
            'columns':x.columns,
            'rows':x.rows
			})
	resources = Resource.query.all()
	return render_template('gridList.html',grids=sorted(grids,key=lambda x:x['name']),editable=True,grid={})

@blueprint.route('/draft', methods=['GET','POST'])
@login_required
@roles_required(['Admin','ProStore'])
def draft():
    if request.method == "POST" and request.form['Submit'] == "Submit":
        for x in request.form:
            if x.startswith("member-"):
                mid = x.split("-")[1]
                v = request.form[x]
                m = Member.query.filter(Member.id == mid).one_or_none()
                if m:
                    m.draft = None if v is None or v.strip() == "" else int(v)
        db.session.commit()
    members = []
    mem = Member.query
    mem = mem.join(Subscription,Subscription.member_id == Member.id)
    mem = mem.filter(Subscription.active=="true")
    mem = mem.filter(Subscription.plan == "pro")
    for x in mem.all():
        sq = db.session.query(func.count(Logs.member_id).label("Count")).filter(Logs.member_id == x.id).group_by(Logs.member_id).one_or_none();
        c = ""
        c += " ".join(x.resource_roles())
        c += " "
        c += " ".join(x.effective_roles())
        members.append( {
            'id':x.id,
            'member':x.member,
            'draft':"" if x.draft is None else x.draft,
            'count':0 if sq is None else sq.Count,
            'comments':c
            })
    return render_template('draft.html',members=members)

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','ProStore'])
def grids_create():
    """(Controller) Create a grid from an HTML form POST"""
    r = StorageGrid()
    r.name = (request.form['input_name'].strip())
    if r.name is None or r.name.strip() == "":
        flash("No name specified","danger")
        return redirect(url_for('prostore.grid'))
    r.short = (request.form['input_short'].strip().title())
    if re.fullmatch("[A-Za-z0-9]+",r.short) is None:
        flash("Invalid character in short code","danger")
        return redirect(url_for('prostore.grid'))
    
    p= request.form['input_columns']
    r.columns = 0
    try:
        r.columns = int(p)
    except:
        pass

    p= request.form['input_aruco']
    r.aruco = 0
    try:
        r.aruco = int(p)
    except:
        pass
    if (r.aruco != 0) and ((r.aruco < 500) or (r.aruco > 999)):
        flash("Grid aruco codes must be 500-999")
        return redirect(url_for('prostore.grid'))

    if r.columns <= 0:
        flash("Invalid number of columns","danger")
        return redirect(url_for('prostore.grid'))

    p= request.form['input_rows']
    r.rows = 0
    try:
        r.rows = int(p)
    except:
        pass

    if r.rows <= 0:
        flash("Invalid number of rows","danger")
        return redirect(url_for('prostore.grid'))

    fixup_grid_locations(None,r.short,r.columns,r.rows,r.aruco)

    db.session.add(r)
    db.session.commit()
    flash("Created.")
    return redirect(url_for('prostore.grid'))

@blueprint.route('/<string:grid>', methods=['GET'])
@roles_required(['Admin','ProStore'])
@login_required
def grids_show(grid):
    """(Controller) Display information about a given grid"""
    r = StorageGrid.query.filter(StorageGrid.short==grid).one_or_none()
    if not r:
        flash("Grid not found")
        return redirect(url_for('prostore.grid'))
    readonly=False
    if (not current_user.privs('ProStore','Finance')):
        readonly=True
    return render_template('grid_edit.html',grid=r,readonly=readonly)


# If oldname is None, creates new locations
# If oldame is specified, renames old locations to new
# Caller must commit!
# If aruco = 0 does not incrementally assign numbers
def fixup_grid_locations(oldname,newname,columns,rows,aruco=0):
    for cc in range(1,columns+1):
        c = chr(64+cc)
        for r in range(1,rows+1):
            newloc = f"{newname}-{c}-{r}"
            if oldname is not None:
                oldloc = f"{oldname}-{c}-{r}"
                #print ("Attempt to find ",oldloc)
                l = ProLocation.query.filter(ProLocation.location == oldloc).one_or_none()
                if l is None:
                    l = ProLocation()
                    l.loctype=0
                    l.location=newloc
                    l.aruco = aruco
                    #print ("ADD LOCATION "+l.location)
                    db.session.add(l)
                elif aruco != l.aruco:
                    l.aruco = aruco
            else:
                l = ProLocation()
                l.loctype=0
                l.location=newloc
                l.aruco=aruco
                db.session.add(l)
            l.location=newloc
            if aruco != 0:
                aruco = aruco + 1

    # Now prune excess locations
    if (oldname is not None and oldname != newname):
        locs = ProLocation.query.filter(ProLocation.location.like(oldname+"-%")).all()
        for l in locs:
            db.session.delete(l)
    elif oldname is not None:
        #print (f"Changing {oldname} to {columns} {rows}")
        locs = ProLocation.query.filter(ProLocation.location.like(oldname+"-%")).all()
        for l in locs:
            #print (f"Found location {l.location}")
            g = re.match("(\w+)-(\w+)-(\d+)",l.location)
            if g is not None:
                c = g.group(2)
                cc = ord(c)-64
                rr = int(g.group(3))
                #print (f"DECIDE {cc} {rr} vs {columns} {rows}")
                if (cc > columns) or ( rr > rows):
                    db.session.delete(l)



    # Caller MUST COMMIT db.session.commit()

@blueprint.route('/<string:grid>', methods=['POST'])
@login_required
@roles_required(['Admin','ProStore'])
def grids_update(grid):
        change = False
        """(Controller) Update an existing grid from HTML form POST"""
        tid = (grid)
        r = StorageGrid.query.filter(StorageGrid.id==tid).one_or_none()
        if not r:
                    flash("Error: Grid not found")
                    return redirect(url_for('prostore.grid'))

        r.name = (request.form['input_name'].strip())
        if r.name is None or r.name.strip() == "":
            flash("No name specified","danger")
            return redirect(url_for('prostore.grid'))
        
        p= request.form['input_columns']
        newcols = 0
        try:
            newcols = int(p)
        except:
            pass

        if newcols <= 0:
            flash("Invalid number of columns","danger")
            return redirect(url_for('prostore.grid'))

        if newcols != r.columns:
            r.columns = newcols
            change=True

        p= request.form['input_rows']
        newrows = 0
        try:
            newrows = int(p)
        except:
            pass

        if newrows <= 0:
            flash("Invalid number of rows","danger")
            return redirect(url_for('prostore.grid'))

        if newrows != r.rows:
            r.rows = newrows
            change=True

        p= request.form['input_aruco']
        newaruco = 0
        try:
            newaruco = int(p)
        except:
            pass

        if r.aruco != newaruco:
            r.aruco = newaruco
            change=True
            flash("fixup aruco start")

        newshort = request.form['input_short'].strip()
        if re.fullmatch("[A-Za-z0-9]+",newshort) is None:
            flash("Invalid character in short code","danger")
            return redirect(url_for('prostore.grid'))
        if newshort != r.short:
            r.short = newshort
            change=True

        if change:
            fixup_grid_locations(r.short,newshort,r.columns,r.rows,r.aruco)

        db.session.commit()
        flash("Grid updated")
        return redirect(url_for('prostore.grid'))

@blueprint.route('/<string:grid>/delete',methods=['GET','POST'])
@roles_required(['Admin','ProStore'])
def grid_delete(grid):
    """(Controller) Delete a grid. Shocking."""
    r = StorageGrid.query.filter(StorageGrid.id == grid).one()
    locs = ProLocation.query.filter(ProLocation.location.like(r.short+"-%")).all()
    for l in locs:
            db.session.delete(l)
    db.session.delete(r)
    db.session.commit()
    flash("Grid deleted.")
    return redirect(url_for('prostore.grid'))

@blueprint.route('/aruco',methods=['GET','POST'])
@roles_required(['Admin','ProStore'])
def aruco():
    return render_template('aruco.html')

## END GRID MANAGEMENT

def cli_randobinz(*cmd,**kvargs):
    import socket,random

    print("Setting draft priorities")
    # Assign all members with current bins to Draft wave 4
    for m in Member.query.join(ProBin,ProBin.member_id == Member.id).all():
        m.draft = 4;

    if (socket.gethostname()  == "staging"):
        print("Running DANGEROUS ops on staging server")
        ProBin.query.delete()
        ProBinChoice.query.delete()
        locs = list(ProLocation.query.all())
        members = Member.query
        members = members.join(Subscription, Subscription.member_id == Member.id)
        members = members.filter(Subscription.rate_plan == "pro" and Subscription.active == "true")
        members = members.all()
        random.shuffle(members)
        for m in members:
            print (m.member)
            random.shuffle(locs)
            for (i,l) in enumerate(locs[0:20]):
                z = ProBinChoice()
                z.member_id = m.id
                z.location_id = l.id
                z.rank=i+1
                db.session.add(z)
    else:
        print("Skiping DANGEROUS operations on non-staging server")

    db.session.commit()

@blueprint.route('/aruco_query_bin/<string:b>',methods=['GET'])
@roles_required(['Admin','ProStore'])
def aruco_query_bin(b):
    try:
        bn = int(b)
    except:
        bn=0
    bins=ProBin.query.filter(ProBin.aruco==bn)
    bins=bins.outerjoin(ProLocation)
    bins=bins.add_column(ProLocation)
    bins=bins.outerjoin(Member)
    bins=bins.add_column(Member)
    r = bins.one_or_none()
    res = {}
    if r is None:
        res['text']=f"Not found"
    else:
        res['text']=f"{r.ProLocation.location} {r.Member.member}"
        res['status'] = singleBinStatus(r.ProBin.id)
        if ('error' in res['status']):
                res['text']+=f"</br><b>Error:{res['status']['error']}</b>"
        

    return (json_dump(res,indent=2), 200, {'Content-type': 'application/json', 'Content-Language': 'en'})

@blueprint.route('/aruco_query_loc/<string:l>',methods=['GET'])
@roles_required(['Admin','ProStore'])
def aruco_query_loc(l):
    try:
        ln = int(l)
    except:
        ln=0

    loc = ProLocation.query.filter(ProLocation.aruco == ln)
    loc=loc.outerjoin(ProBin,ProLocation.id == ProBin.location_id)
    loc=loc.add_column(ProBin)
    loc=loc.outerjoin(Member)
    loc=loc.add_column(Member)
    loc = loc.one_or_none()
    res = {}

    if loc is None:
        res['text'] = f"Aruco {ln} not found"
    else:
        if loc.ProLocation is not None:
            res['loc_id'] = loc.ProLocation.id
        if loc.Member is None:
            res['text'] = f"{loc.ProLocation.location}"
        else:
            res['text'] = f"{loc.ProLocation.location} {loc.Member.member}"
        if loc.ProBin is not None:
            res['bin_id'] = loc.ProBin.id

    return (json_dump(res,indent=2), 200, {'Content-type': 'application/json', 'Content-Language': 'en'})


@blueprint.route('/aruco_query/<string:b>/<string:l>',methods=['GET'])
@roles_required(['Admin','ProStore'])
def aruco_query(b,l):
    try:
        bn = int(b)
    except:
        bn=0
    try:
        ln = int(l)
    except:
        ln=0
    bin = ProBin.query.filter(aruco==bn).one_or_none()

    loc = ProLocation.query.filter(ProLocation.aruco == ln)
    loc=loc.outerjoin(ProBin,ProLocation.id == ProBin.location_id)
    loc=loc.add_column(ProBin)
    loc=loc.one_or_none()

    bins=ProBin.query.filter(ProBin.aruco==bn)
    bins=bins.outerjoin(ProLocation)
    bins=bins.add_column(ProLocation)
    bins=bins.outerjoin(Member)
    bins=bins.add_column(Member)
    r = bins.one_or_none()
    res = {}
    if r is None:
        res['text']=f"Not found"
    else:
        res['text']=f"{r.ProLocation.location} {r.Member.member}"
        res['bin_id']= r.ProBin.id,

    if loc is None:
        res['text'] += f"</br>Location: Aruco {ln} not found"
    else:
        res['text'] += f"</br>Location: {ln} is {loc.ProLocation.location}"
        res['loc_id']= loc.ProLocation.id
        res['location']= loc.ProLocation.location

    
    if loc is not None and loc.ProLocation is not None and r is not None:
        if (r.ProBin.location_id != loc.ProLocation.id):
            if loc.ProBin is None:
                res['text'] += f"</br><b>Mismatch:</b> Bin should be in {r.ProLocation.location} EMPTY"
                res['move_to_loc'] = r.ProBin.id
            else:
                res['text'] += f"</br><b>Mismatch:</b> Bin should be in {r.ProLocation.location}"
        else:
            res['text'] += f"</br><b>Correct</b>"

    print ("LOC",loc)
    print ("BIN",r)


    return (json_dump(res,indent=2), 200, {'Content-type': 'application/json', 'Content-Language': 'en'})

    

def register_pages(app):
  app.register_blueprint(blueprint)
