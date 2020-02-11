# vim:expandtab:shiftwidth=2:tabstop=2:softtabstop=2
from ..templateCommon import  *
import random
import string
import datetime
from ..slackutils import add_user_to_channel

blueprint = Blueprint("training", __name__, template_folder='templates', static_folder="static",url_prefix="/training")

@blueprint.route('/', methods=['GET'])
@login_required
def training():
  res = Resource.query.all()
  sa = []
  for r in res:
    if r.sa_url:
      # This resrouce supports self-authorization
      ma = AccessByMember.query.filter(AccessByMember.member_id == current_user.id,AccessByMember.resource_id == r.id).one_or_none()
      ar = {'resource':r.description,'rid':r.id,'status':'?','url':r.sa_url,'quiz_url':url_for('training.quiz',resource=r.name)}
      if ma:
        if ma.level == 0: 
          ar['desc'] = 'You are already authorized'
          ar['status'] = 'already'
        elif ma.level == -2:  
          ar['desc'] = 'Access already pending'
          ar['status'] = 'cannot'
        elif ma.level == -1:  
          ar['desc'] = 'Authorization was revoked'
          ar['status'] = 'cannot'
        elif ma.level >0: 
          ar['desc'] = 'Your are a Resource Manager'
          ar['status'] = 'already'
      else:
        #User has no access - can they train?
        if (r.sa_required):
          # They need to have authorization on an existing resource
          ma2 = AccessByMember.query.filter(AccessByMember.member_id == current_user.id,AccessByMember.resource_id == r.sa_required).one_or_none()
          r2 = Resource.query.filter(Resource.id == r.sa_required).one_or_none()
          if r2 == None:
            logger.error("Prerequisite resource broken")
            ar['desc'] = 'Prerequisite resource broken (Seek help!)'
            ar['status'] = 'cannot'
          elif ma2 == None:
            ar['desc'] = 'Need to first be authorized on '+r2.description
            ar['status'] = 'cannot'
          elif ma2.level < 0:
            ar['desc'] = 'You are restricted from using '+r2.description
            ar['status'] = 'cannot'
          else:
            # They are authorized on prerequite resource..
            ar['desc'] = 'Training Availalble'
            ar['status'] = 'can'
            # ...unless they don't meet days/hours requirements...
            if (r.sa_hours) > 0:
              q = UsageLog.query.filter(UsageLog.resource_id==r2.id)
              q = q.filter(UsageLog.time_logged >= datetime.datetime.now()-datetime.timedelta(days=365*2))
              q = q.filter(UsageLog.member_id == current_user.id)

              q = q.add_column(func.sum(UsageLog.enabledSecs).label('enabled'))
              q = q.add_column(func.sum(UsageLog.activeSecs).label('active'))
              q = q.add_column(func.sum(UsageLog.idleSecs).label('idle'))
              q= q.one_or_none()
              #print q
              idle_hours=0
              active_hours=0
              enabled_hours=0
              if q:
                idle_hours = int(q[1]/3600)
                active_hours = int(q[2]/3600)
                enabled_hours = int(q[3]/3600)
              total_hours=idle_hours+active_hours+enabled_hours
              #print "IDLE",idle_hours,"ACTIVE",active_hours,"ENABLED",enabled_hours,"TOTAL",total_hours
              if total_hours < r.sa_hours:
                ar['desc'] = 'Must meet expereince prerequisites on '+r2.description
                ar['status'] = 'cannot'
            if (r.sa_days) > 0:
              # Check how long they have been authorized for
              q = Logs.query.filter(Logs.resource_id==r2.id)
              q = q.filter(Logs.event_type == eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id)
              q = q.filter(Logs.member_id == current_user.id)
              q = q.order_by(Logs.time_reported.asc())
              q = q.limit(1)
              x = q.one_or_none()
              if x:
                #print x.time_logged,x.time_reported
                d =  (datetime.datetime.now()-x.time_logged).days
                #print "AUTHO FOR",d
                if d < r.sa_days:
                  ar['desc'] = 'Must meet expereince prerequisites on '+r2.description
                  ar['status'] = 'cannot'

        else:
          ar['desc'] = 'Training Availalble'
          ar['status'] = 'can'

        if ar['status'] == 'can':
          # Make sure quiz is oky
          q = ResourceQuiz.query.filter(ResourceQuiz.resource_id == r.id).count()
          if (q==0):
            ar['desc'] = 'Quiz is not ready - See Resource Manager'
            ar['status'] = 'cannot'
      
      sa.append(ar)

  #print sa
  return render_template('training.html',training=sa)

@blueprint.route('/editquiz', methods=['GET','POST'])
@login_required
def editquiz():
	if request.method == "POST" and request.form:
		for x in request.form:
			print x,request.form[x]
		if 'resource_id' in request.form and request.form['resource_id']:
			rid = int(request.form['resource_id'])
			i=1
			o=0
			ResourceQuiz.query.filter(ResourceQuiz.resource_id == rid).delete()
			while True:
				if 'question_'+str(i) not in request.form or 'answer_'+str(i) not in request.form:
					break
				q=request.form['question_'+str(i)].strip()
				a=request.form['answer_'+str(i)].strip().lower()
				i+=1
				if q != "" or a !="":
					print "GOT",i,o,q,a
					o+=1
					n = ResourceQuiz(answer=a,question=q,idx=o,resource_id=rid)
					db.session.add(n)
			db.session.commit()
			flash("Saved","success")
	res = Resource.query.filter(Resource.id == request.values['resid']).one_or_none()
	questions = ResourceQuiz.query.filter(ResourceQuiz.resource_id == res.id).order_by(ResourceQuiz.idx).all()
	return render_template('quiz_edit.html',res=res,training={},questions=questions)

@blueprint.route('/quiz/<string:resource>', methods=['GET','POST'])
@login_required
def quiz(resource):
  hilight=False
  r = Resource.query.filter(Resource.name == resource).one_or_none()
  if not r:
    flash("No resrouce","warning")
    return redirect(url_for('empty'))
  qz = ResourceQuiz.query.filter(ResourceQuiz.resource_id == r.id).all()
  if len(qz) == 0:
    flash("Quiz is missing - contact Resource Manager","warning")
    return redirect(url_for('empty'))
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
      cnt = AccessByMember.query.filter((AccessByMember.member_id == current_user.id) & (AccessByMember.resource_id == r.id)).count()
      if cnt == 0:
        ac = AccessByMember(member_id = current_user.id,resource_id = r.id,level=0)
        db.session.add(ac)
        flash("Congratulations! You are authorized!","success")
        authutil.log(eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id,resource_id=r.id,message="Self-Auth",member_id=current_user.id,commit=0)
          
        db.session.commit()
        authutil.kick_backend()
        if r.slack_chan and r.slack_chan.strip() != "":
          add_user_to_channel(r.slack_chan,current_user)
      else:
        flash("Access record already exists","warning")
      return redirect(url_for('training.training'))

	return render_template('quiz.html',resource=r,quiz=quiz,highlight=hilight)
    

def register_pages(app):
	app.register_blueprint(blueprint)
