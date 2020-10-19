# vim:expandtab:shiftwidth=2:tabstop=2:softtabstop=2
from ..templateCommon import  *
import random
import string
import datetime
from authlibs import accesslib
from ..slackutils import add_user_to_channel

blueprint = Blueprint("training", __name__, template_folder='templates', static_folder="static",url_prefix="/training")

# Checks if a user can take the selected training
def verify_training(train,user=current_user):
  print "NEW"
  ar={'status':'error'}
  quizname = ""
  resource = Resource.query.filter(Resource.id == train.resource_id).one_or_none()
  if not resource:
    return result; # error

  ma = AccessByMember.query.filter(AccessByMember.member_id == user.id,AccessByMember.resource_id == resource.id).one_or_none()
  if train.name and train.name.strip() != "":
    quizname=train.name
  else:
    quizname = resource.short.title()
    if train.endorsements and train.endorsements.strip() != "":
      quizname += " " + train.endorsements + " Endorsement"
    else:
      quizname += " General Authorization"
  ar = {'name':quizname,'resource':resource.short.title(),
        'rid':train.id,'status':'?','url':train.url,
        'quiz_url':url_for('training.quiz',quizid=train.id),
        'quizname':quizname}

  # Are they trying to get an endorsement?
  if train.endorsements and train.endorsements.strip() != "":
    if not ma:
      # They don't have any access to this at all
      ar['desc'] = 'Training Available'
      ar['status'] = 'can'
    else:
      # Doing and endorsement
      if ma.lockout_reason == "Self-Trained":
        ar['desc'] = 'General Authorization Pending'
        ar['status'] = 'already'
      elif ma.lockout_reason and ma.lockout_reason.strip() != "":
        ar['desc'] = 'Access Susspended'
        ar['status'] = 'cannot'
      elif ma.level == -1:  
        ar['desc'] = 'Authorization was revoked'
        ar['status'] = 'cannot'
      else:
        if ma.permissions:
          # They have some endorsements, but the right one(s)?
          e =  ma.permissions.strip().split()
          for p in  train.endorsements.strip().split():
            print "CHECK",e,p,ar['status']
            if "pending_"+p in e:
              print "WE MAYBE CAN"
              if ar['status'] != 'can':
                # Only if we haven't already determined it's needed!
                ar['desc'] = 'Already Pending'
                ar['status'] = 'already'
            elif p in e:
              if ar['status'] != 'can':
                # Only if we haven't already determined it's needed!
                ar['desc'] = 'Already Have'
                ar['status'] = 'already'
            else:
              # Neither pending nor granted
              ar['desc'] = 'Training Available'
              ar['status'] = 'can'
        else:
          # They don't have any endorsements at all (yet)
          ar['desc'] = 'Training Available'
          ar['status'] = 'can'

  # Are they trying to get General Auth
  elif ma:
    if ma.lockout_reason == "Self-Trained":
      ar['desc'] = 'Authorization Pending'
      ar['status'] = 'already'
    elif ma.lockout_reason and ma.lockout_reason.strip() != "":
      ar['desc'] = 'Access Susspended'
      ar['status'] = 'cannot'
    elif ma.level == 0: 
      ar['desc'] = 'Authorized'
      ar['status'] = 'already'
    elif ma.level == -2:  
      ar['desc'] = 'Access is pending'
      ar['status'] = 'cannot'
    elif ma.level == -1:  
      ar['desc'] = 'Authorization was revoked'
      ar['status'] = 'cannot'
    elif ma.level >0: 
      ar['desc'] = 'You are a Resource Manager'
      ar['status'] = 'already'
  # "else" here means they are trying for general auth and have no existig acces record (ma)
  else:
    ar['desc'] = 'Training Available'
    ar['status'] = 'can'


  ## If they 'can' train - let's check prerequisites
  if ar['status'] == 'can':
    if (train.required):
      # They need to have authorization on an existing resource
      ma2 = AccessByMember.query.filter(AccessByMember.member_id == user.id,AccessByMember.resource_id == train.required).one_or_none()
      r2 = Resource.query.filter(Resource.id == train.required).one_or_none()
      if r2 == None:
        logger.error("Prerequisite resource broken")
        ar['desc'] = 'Prerequisite resource broken (Seek help!)'
        ar['status'] = 'cannot'
      elif ma2 == None:
        ar['desc'] = 'Need to first be authorized on '+r2.short.title()
        ar['status'] = 'cannot'
      elif ma2.level < 0:
        ar['desc'] = 'You are restricted from using '+r2.short.title()
        ar['status'] = 'cannot'
      else:
        # They are authorized on prerequite resource..
        ar['desc'] = 'Training Availalble'
        ar['status'] = 'can'

        # ...Do theyrequire an required endorsement...
        if train.required_endorsements and train.required_endorsements.strip() != "":
          # Assume endorsement missing until we find below
          ar['desc'] = 'Requires %s endorsement on %s' % (train.required_endorsements.strip(),r2.short.title())
          ar['status'] = 'cannot'
          print resource.short,"REQUIRES",train.required_endorsements,"on",r2.short,"HAVE",ma2.permissions
          for e in train.required_endorsements.strip().split():
            if ma2.permissions and ma.permissions.strip() != "":
              for e2 in ma.permissions.strip().split():
                if e2 == e:
                  ar['desc'] = 'Training Availalble'
                  ar['status'] = 'can'
            
            
        # ...or they don't meet days/hours requirements...
        if r2 and (train.hours > 0):
          q = UsageLog.query.filter(UsageLog.resource_id==r2.id)
          q = q.filter(UsageLog.time_logged >= datetime.datetime.now()-datetime.timedelta(days=365*2))
          q = q.filter(UsageLog.member_id == user.id)

          q = q.add_column(func.sum(UsageLog.enabledSecs).label('enabled'))
          q = q.add_column(func.sum(UsageLog.activeSecs).label('active'))
          q = q.add_column(func.sum(UsageLog.idleSecs).label('idle'))
          q= q.one_or_none()
          #print q
          idle_hours=0
          active_hours=0
          enabled_hours=0
          if q:
            if q[1]: idle_hours = int(q[1]/3600)
            if q[2]: active_hours = int(q[2]/3600)
            if q[3]: enabled_hours = int(q[3]/3600)
          total_hours=idle_hours+active_hours+enabled_hours
          #print "IDLE",idle_hours,"ACTIVE",active_hours,"ENABLED",enabled_hours,"TOTAL",total_hours
          if total_hours < train.hours:
            ar['desc'] = 'Must meet expereince prerequisites on '+r2.description
            ar['status'] = 'cannot'
        if r2 and (train.days > 0):
          # Check how long they have been authorized for
          q = Logs.query.filter(Logs.resource_id==r2.id)
          q = q.filter(Logs.event_type == eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id)
          q = q.filter(Logs.member_id == user.id)
          q = q.order_by(Logs.time_reported.asc())
          q = q.limit(1)
          x = q.one_or_none()
          if x:
            #print x.time_logged,x.time_reported
            d =  (datetime.datetime.now()-x.time_logged).days
            #print "AUTHO FOR",d
            if d < train.days:
              ar['desc'] = 'Must meet expereince prerequisites on '+r2.description
              ar['status'] = 'cannot'

    else:
      ar['desc'] = 'Training Availalble'
      ar['status'] = 'can'

    if ar['status'] == 'can':
      # Make sure quiz is oky
      q = QuizQuestion.query.filter(QuizQuestion.training_id == train.id).count()
      if (q==0):
        ar['desc'] = 'Quiz is not ready - See Resource Manager'
        ar['status'] = 'cannot'

  return ar
  


@blueprint.route('/', methods=['GET'])
@login_required
def training():
  courses = Training.query.outerjoin(Resource,Resource.id == Training.resource_id).all()
  sa = []
  for t in courses:
      ar = verify_training(t)
      if ar['url']:
        sa.append(ar)

  return render_template('training.html',training=sa)

@blueprint.route('/approvals/<string:resname>', methods=['GET','POST'])
@login_required
def approvals(resname):
  res = Resource.query.filter(Resource.name == resname).one_or_none()
  if not res:
    flash ("Invalid resource id","warning")
    return redirect(url_for('index'))
	if request.method == "POST" and request.form:
    print request.form
    authorize=True
    if 'deny' in request.form: authorize=False
    for x in request.form:
      if x.startswith("id_"):
        xx = x.split("_")
        i = int(xx[1])
        endo = None
        if len(xx) == 3:
          endo = xx[2].strip()
        print "Authorize" if authorize else "Deny",i,endo
        a = AccessByMember.query.filter((AccessByMember.member_id == i) & (AccessByMember.resource_id == res.id)).one_or_none()
        endos = []
        if a.permissions:
          endos = a.permissions.strip().split()
        if a:
          if authorize:
            if endo:
              endos.remove("pending_"+endo)
              if endo not in endos:
                endos.append(endo)
                authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,resource_id=res.id,message="Self-Auth %s Endorsement Approved" % endo,member_id=current_user.id,commit=0)
            else:
              authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,resource_id=res.id,message="Self-Auth Approved",member_id=current_user.id,commit=0)
            a.lockout_reason =None 
          else:
            authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_REVOKED.id,resource_id=res.id,message="Self-Auth Denied",member_id=current_user.id,commit=0)
            db.session.delete(a)
        else: # No access record exists
          if authorize:
            a = AccessByMember(member_id =i,resource_id=res.id)
            if endo:
              endos.append(endo)
        if a:
          a.permissions = " ".join(endos)
    db.session.commit()
    authutil.kick_backend()
    flash("Done")
    return redirect(url_for('index'))
  else:
    # Find anyone pending on "General Access" - i.e. they will appear "suspended"
    m = AccessByMember.query.filter((AccessByMember.resource_id == res.id))
    m = m.outerjoin(Member).add_columns(Member.lastname,Member.firstname)
    users = m.all()
    u = []
    for m in users:
      acc=m[0]
      if acc.lockout_reason and acc.lockout_reason.strip() == "Self-Trained":
        u.append({'id':m[0].member_id,'name':m[2]+" "+m[1],"desc":"General Access"})
      if acc.permissions:
        for e in acc.permissions.strip().split():
          if e.startswith("pending_"):
            name = e.replace("pending_","")
            u.append({'id':m[0].member_id,'name':m[2]+" "+m[1],"desc":name+" Endorsement","type":name})

    return render_template('pending.html',resources=res,users=u)

#Populate training record from web form
def populate_train(train,request):
  if (request.form['input_days'].strip() != ""):
    train.days = int(request.form['input_days'])
  else:
    train.days = None

  if (request.form['input_hours'].strip() != ""):
    train.hours = int(request.form['input_hours'])
  else:
    train.hours = None

  if (request.form['input_permit'].strip() != ""):
    train.permit = int(request.form['input_permit'])
  else:
    train.permit = 0

  if (int(request.form['input_required']) != -1):
    train.required = int(request.form['input_required'])
  else:
    train.required = None

  train.name = request.form['input_name'].strip()
  train.url = request.form['input_url'].strip()
  if train.url == "":
    flash ("Warning - Training URL not specified - Course will not appear in portal!","danger")
  elif not train.url.lower().startswith("http://") and not train.url.lower().startswith("https:"):
    flash ("Warning - Training URL was invalid!","danger")
  train.endorsements = request.form['input_endorsements'].strip()
  if 'input_required_endorsements' in request.form:
    train.required_endorsements = request.form['input_required_endorsements'].strip()
  else:
    train.required_endorsements = None
  

# Train MUST already be "added" and have an index!
def populate_quiz(train,request):
    i=1
    o=0
    while True:
      if 'question_'+str(i) not in request.form or 'answer_'+str(i) not in request.form:
        break
      q=request.form['question_'+str(i)].strip()
      a=request.form['answer_'+str(i)].strip().lower()
      if q == "" and a == "": flash("Empty question %s removed"%i,"warning")
      elif q == "": flash("Question %s was blank - removed"%i,"warning")
      elif a == "": flash("Question %s had no answer - removed"%i,"warning")
      i+=1
      if q != "" and a !="":
        #print "GOT",i,o,q,a
        o+=1
        n = QuizQuestion(answer=a,question=q,idx=o,training_id=train.id)
        db.session.add(n)
    if o==0:
      flash("No questions provided - Course will not work!","danger")

@blueprint.route('/newquiz/<string:resname>', methods=['GET','POST'])
@login_required
def newquiz(resname):
  res = Resource.query.filter(Resource.name == resname).one()
  if accesslib.user_privs_on_resource(member=current_user,resource=res) < AccessByMember.LEVEL_ARM:
    flash("You are not authorized to edit this quiz","warning")
    return redirect(url_for('training.training'))

	if request.method == "POST" and request.form:
		#for x in request.form:
		#	print "POSTED",x,request.form[x]
    i=1
    o=0
    train = Training(resource_id=res.id)
    populate_train(train,request)
    db.session.add(train)
    db.session.flush()
    populate_quiz(train,request)
    db.session.commit()
    return redirect(url_for('training.editquiz',trainid=train.id))

  resources = Resource.query.all()
	return render_template('quiz_edit.html',resources=resources,res=res,rec={},questions=[])
  
@blueprint.route('/editquiz/<int:trainid>', methods=['GET','POST'])
@login_required
def editquiz(trainid):
  train = Training.query.filter(Training.id == trainid).one_or_none()
  if not train:
    flash("Error: Does not exist","warning")
    return redirect(url_for('training.training'))
  rid = train.resource_id
  
	if request.method == "POST" and request.form:
		#for x in request.form:
		#	print "POSTED",x,request.form[x]
    if accesslib.user_privs_on_resource(member=current_user,resource_id=rid) < AccessByMember.LEVEL_ARM:
      flash("You are not authorized to edit this quiz","warning")
      return redirect(url_for('training.training'))


    populate_train(train,request)

    QuizQuestion.query.filter(QuizQuestion.training_id == trainid).delete()

    populate_quiz(train,request)
    db.session.commit()
    flash("Saved","success")
	res = Resource.query.filter(Resource.id == rid).one_or_none()

  if accesslib.user_privs_on_resource(member=current_user,resource=res) < AccessByMember.LEVEL_ARM:
    flash("You are not authorized to edit this quiz","warning")
    return redirect(url_for('training.training'))

  resources = Resource.query.all()
	questions = QuizQuestion.query.filter(QuizQuestion.training_id == trainid).order_by(QuizQuestion.idx).all()
	return render_template('quiz_edit.html',resources=resources,res=res,rec=train,questions=questions)

@blueprint.route('/delete/<int:trainid>', methods=['GET','POST'])
@login_required
def training_delete(trainid):
  train = Training.query.filter(Training.id == trainid).one_or_none()
  if not train:
    flash("Error: Does not exist","alert")
    return redirect(url_for('training.training'))
  rid = train.resource_id
  res = Resource.query.filter(Resource.id == rid).one()
  if accesslib.user_privs_on_resource(member=current_user,resource_id=rid) < AccessByMember.LEVEL_ARM:
    flash("You are not authorized to edit this quiz","alert")
    return redirect(url_for('training.training'))
  db.session.delete(train)
  db.session.commit()
  flash("Deleted","success")
  return redirect(url_for('resources.resource_show',resource=res.name))

@blueprint.route('/endorsements/<string:resid>')
@login_required
def get_endorsements(resid):
  res=[]
  e = Resource.query.filter(Resource.id==int(resid)).one()
  if e.permissions:
    res = e.permissions.strip().split()
	return json_dump(res, 200, {'Content-type': 'application/json', 'Content-Language': 'en'},indent=2)

  
  

@blueprint.route('/quiz/<int:quizid>', methods=['GET','POST'])
@login_required
def quiz(quizid):
  hilight=False
  train = Training.query.filter(Training.id == quizid).one_or_none()
  if not train:
    flash("No course found","warning")
    return redirect(url_for('empty'))
  res = Resource.query.filter(Resource.id == train.resource_id).one();
  qz = QuizQuestion.query.filter(QuizQuestion.training_id == train.id).all()
  if len(qz) == 0:
    flash("Quiz has no questions - contact Resource Manager","warning")
    return redirect(url_for('training.training'))

  # Are you authorized to take this quiz??
  ar = verify_training(train)
  if ar['status'] != 'can':
     flash(ar['desc'])
     return redirect(url_for('training.training'))

  quiz=[]
  for (i,x) in enumerate(qz):
    quiz.append({'question':x.question,'answer':x.answer})
  
  if request.method == "POST":
    wc=0
    for (i,x) in enumerate(quiz):
        a = request.form['input_answer_'+str(i+1)]
        if a.strip().lower() != x['answer'].strip().lower():
          quiz[i]['mark'] = 'wrong'
          wc += 1
        else:
          quiz[i]['mark'] = 'correct'
        quiz[i]['input_answer'] = a
    if 'acknowledge' not in request.form:
      hilight=True
    if wc == 0 and hilight == False:
      ac = AccessByMember.query.filter((AccessByMember.member_id == current_user.id) & (AccessByMember.resource_id == res.id)).one_or_none()
      if not ac:
        if train.permit == 1:
          ac = AccessByMember(member_id = current_user.id,resource_id = train.resource_id,level=0,lockout_reason="Self-Trained")
          db.session.add(ac)
          flash("Training successful - Awaiting RM approval to authorize","success")
          authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,resource_id=train.resource_id,message="Self-Auth - Pending",member_id=current_user.id,commit=0)
        else:
          ac = AccessByMember(member_id = current_user.id,resource_id = train.resource_id,level=0)
          db.session.add(ac)
          flash("Congratulations! You are authorized!","success")
          authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,resource_id=train.resource_id,message="Self-Auth",member_id=current_user.id,commit=0)
          
        if res.slack_chan and res.slack_chan.strip() != "":
          add_user_to_channel(r.slack_chan,current_user)


      # Add Endorsements (if we need to)
      if train.endorsements:
        if not ac.permissions: 
          existing=[]
        else:
          existing = ac.permissions.strip().split()
        for n in train.endorsements.strip().split():
          if train.permit == 1:
            # No automatic auth
            if n not in existing and "pending_"+n not in existing:
              existing.append("pending_"+n)
              authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,resource_id=train.resource_id,message="Pending %s Endorsement" % n,member_id=current_user.id,commit=0)
            else:
              if n in existing: flash("You already have %s endoresment" % n)
              if "pending_"+n in existing: flash("%s endoresment is already pending RM approval" % n)
          else:
            # Automatic auth
            if "pending_"+n in existing: existing.remove("pending_"+n)
            print "AUTO",n,"IN",existing
            if n not in existing:
              print "ADD EXIST"
              existing.append(n)
              authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,resource_id=train.resource_id,message="Self-Auth %s Endorsement" % n,member_id=current_user.id,commit=0)
        ac.permissions=" ".join(existing)
      db.session.commit()
      authutil.kick_backend()
      return redirect(url_for('training.training'))

	return render_template('quiz.html',resource=res,training=train,quiz=quiz,highlight=hilight)
    

def register_pages(app):
	app.register_blueprint(blueprint)
