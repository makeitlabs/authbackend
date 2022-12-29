# vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint, Markup
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, Resource, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs, ApiKey
from functools import wraps
import json
#from .. import requireauth as requireauth
from .. import utilities as authutil
from .. import google_admin 
from ..utilities import _safestr as safestr
from authlibs import eventtypes
from authlibs import payments as pay
from datetime import datetime
from .. import membership

from authlibs.templateCommon import *

from sqlalchemy import case, DateTime


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("payments", __name__, template_folder='templates', static_folder="static",url_prefix="/payments")


# ------------------------------------------------
# Payments controllers
# Routes:
#  /payments - Show payments options
# ------------------------------------------------

@blueprint.route('/', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def payments():
    """(Controller) Show Payment system controls"""
    cdate = pay.getLastUpdatedDate()
    return render_template('payments.html',cdate=cdate)

# "Missing" payments - i.e. subcriptions without a known member
@blueprint.route('/missing/assign/<string:assign>', methods = ['GET'])
@blueprint.route('/missing', methods = ['GET','POST'])
@login_required
@roles_required(['Admin','Finance'])
def payments_missing(assign=None):
    """Find subscriptions with no members"""
    if 'Undo' in request.form:
        s = Subscription.query.filter(Subscription.membership == request.form['membership']).one()
        if s.member_id:
          authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_PAYMENT_UNLINKED.id,message="Undo",member_id=s.member_id,doneby=current_user.id,commit=0)
        s.member_id = None
        authutil.kick_backend()
        db.session.commit()
        flash ("Undone.")
    if 'Assign' in request.form:
        if 'member' not in request.form or 'membership' not in request.form:
            flash("Must select a member and a subscription to link")
        elif request.form['member']=="" or request.form['membership']=="":
            flash("Must select a member and a subscription to link")
        else:
            m = Member.query.filter(Member.member == request.form['member']).one()
            m.membership=request.form['membership']
            s = Subscription.query.filter(Subscription.membership == request.form['membership']).one()
            s.member_id = db.session.query(Member.id).filter(Member.member == request.form['member'])
            authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_PAYMENT_LINKED.id,member_id=m.id,doneby=current_user.id,commit=0)
            db.session.commit()
            btn = '<form method="POST"><input type="hidden" name="membership" value="%s" /><input type="submit" value="Undo" name="Undo" /></form>' % request.form['membership']
            authutil.kick_backend()
            flash(Markup("Linked %s to %s %s" % (request.form['member'],request.form['membership'],btn)))

    subscriptions = Subscription.query.filter(Subscription.member_id == None).all()
    members = Member.query.outerjoin(Subscription).filter(Subscription.member_id == None)
    if 'applymemberfilter' in request.form:
        members = members.filter(Member.member.ilike("%"+request.form['memberfilter']+"%"))
    members = members.all()
    """Find members with no members"""


    return render_template('payments_missing.html',subscriptions=subscriptions,members=members)

@blueprint.route('/manual', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def manual_payments():
   sqlstr = """select member,plan,expires_date,updated_date from payments where paysystem = 'manual'"""
   members = query_db(sqlstr)
   return render_template('payments_manual.html',members=members)


@blueprint.route('/manual/extend/<member>', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def payments_manual_extend(member):
    safe_id = safestr(member)
    sqlstr = "update payments set expires_date=DATETIME(expires_date,'+31 days') where member = '%s' " % safe_id
    execute_db(sqlstr)
    get_db().commit()
    flash("Member %s was updated in the payments table" % safe_id)
    return redirect(url_for('payments.manual_payments'))

@blueprint.route('/manual/expire/<member>', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def payments_manual_expire(member):
    safe_id = safestr(member)
    sqlstr = "update payments set expires_date=datetime('now')  where member = '%s' " % safe_id
    execute_db(sqlstr)
    get_db().commit()
    # TODO: EXPIRE MEMBER FROM ACCESS CONTROLS
    flash("Member %s was forcibly expired" % safe_id)
    return redirect(url_for('payments.manual_payments'))

@blueprint.route('/manual/delete/<member>', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def payments_manual_delete(member):
    safe_id = safestr(member)
    sqlstr = "delete from payments where member = '%s' " % safe_id
    execute_db(sqlstr)
    get_db().commit()
     # TODO: EXPIRE MEMBER FROM ACCESS CONTROLS
    flash("Member %s was deleted from the payments table" % safe_id)
    return redirect(url_for('payments.manual_payments'))

@blueprint.route('/test', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def test_payments():
   """(Controller) Validate the connection to the payment system(s)"""
   if pay.testPaymentSystems():
      flash("Payment system is reachable.")
   else:
      flash("Error: One or more Payment systems is Unreachable, review logs.")
   return redirect(url_for('payments.payments'))

@blueprint.route('/membership/<string:membership>', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def payment_membership(membership):
   (subscription,member)=db.session.query(Subscription,Member).outerjoin(Member).filter(Subscription.membership==membership).one_or_none()
   return render_template('payments_membership.html',subscription=subscription,member=member)

@blueprint.route('/update', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def update_payments():
    """(Controller) Sync Payment data and update Member data (add missing, deactivate, etc)"""
    # TODO: Error handling
    pay.updatePaymentData()
    isTest=False
    if current_app.config['globalConfig'].DeployType.lower() != "production":
      isTest=True
      logger.error("Non-Production environment - NOT creating google/slack accounts")
    membership.syncWithSubscriptions(isTest)
    authutil.kick_backend()
    flash("Payment and Member data adjusted")
    return redirect(url_for('payments.payments'))

@blueprint.route('/<string:id>', methods=['GET'])
@login_required
@roles_required(['Admin','Finance'])
def payments_member(id):
    pid = safestr(id)
    # Note: When debugging Payments system duplication, there may be multiple records
    #  Display template is set up to handle that scenario
    sqlstr = """select p.member, m.firstname, m.lastname, p.email, p.paysystem, p.plan, p.customerid,
            p.expires_date, p.updated_date, p.checked_date, p.created_date from payments p join
            members m on m.member=p.member where p.member='%s'""" % pid
    #user = Subscription.query.filter(
    return render_template('payments_member.html',user=user)

@blueprint.route('/reports', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def payments_reports():
    """(Controller) View various Payment data attributes"""
    f = request.args.get('filter','')
    sqlstr = "select * from payments"
    if f !='':
        if f == 'expired':
            sqlstr = sqlstr + " where expires_date < Datetime('now')"
        elif f == 'notexpired':
            sqlstr = sqlstr + " where expires_date > Datetime('now')"
        elif f == 'recentexpired':
            sqlstr = sqlstr + " where expires_date > Datetime('now','-180 days') AND expires_date < Datetime('now')"
        elif f == 'recentexpired':
            sqlstr = sqlstr + " where expires_date > Datetime('now','-180 days') AND expires_date < Datetime('now')"
    payments = query_db(sqlstr)
    return render_template('payments_reports.html',f=f,payments=payments)

@blueprint.route('/fees', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def payments_fees():
    """(Controller) Charge Fee to a user, Schedule recurring Fee, view past paid fees"""
    f = request.args.get('days','90')
    # TODO: Member ID, pass in from member page?
    member = {}
    dt = """Datetime('now','-%s days')""" % f
    sqlstr = """select member, amount, fee_date, fee_name, fee_group, fee_description from feespaid where fee_date > %s""" % dt
    fees = query_db(sqlstr)
    return render_template('fees.html',days=f,member=member,fees=fees)

@blueprint.route("/fees/charge", methods = ['POST'])
@login_required
@roles_required(['Admin','Finance'])
def payments_fees_charge():
    """(Controller) Charge a one-time fee to a user"""
    fee = {}
    mandatory_fields = ['memberid','amount','name','description','group']
    for f in mandatory_fields:
        fee[f] = ''
        if f in request.form:
            fee[f] = safestr(request.form[f])
            print(fee[f])
        if fee[f] == '':
            flash("Error: One or more mandatory fields not filled out")
            return redirect(url_for('payments.payments_fees'))
    # Validate member
    sqlstr = "Select customerid from payments where member = '%s'" % fee['memberid']
    members = query_db(sqlstr,"",True)
    if members:
        # Force validation of currency value
        try:
            "{:.2f}".format(float(fee['amount']))
            ## TODO: Still need to create the actual charge
            result = pay.chargeFee(paysystem,members['customerid'],fee['name'],fee['group'],fee['description'],fee['amount'])
            if result['success'] == True:
                # TODO: Record fee charge
                flash("Fee successfully charged and recorded")
            else:
                flash("Error: Could not charge fee")
        except ValueError:
            flash("Amount must be a currency value such as 75 or 13.11")
        #
    else:
        flash("Error: Memberid does not exist. Make sure you have the right one..")
    return redirect(url_for('payments.payments_fees'))

@blueprint.route('/relate', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def relate():
  mem=None
  if 'member_id' in request.values:
    mid = int(request.values['member_id'])
    mem = Member.query.filter(Member.id==mid).one_or_none()
  subscriptions = Subscription.query.filter(Subscription.member_id == None).filter(Subscription.active == "true").all()

  return render_template('payments_relate.html',subscriptions=subscriptions,linkmember=mem)

# Post handler for "relate" above
@blueprint.route('/relate_assign', methods = ['POST'])
@login_required
@roles_required(['Admin','Finance'])
def relate_assign():
  if 'Create' in request.form:
      newm={
        'first':request.form['firstname'],
        'last':request.form['lastname'],
        'email':request.form['email'],
        'plan':request.form['plan'],
        'rate_plan':request.form['rate_plan'],
        'alt_email':request.form['alt_email'],
        'membership':request.form['membership'],
        'no_email':False
      }
      if 'no_email' in request.form: newm['no_email']=True
      # Last checks
      error=False
      if newm['first'] == "": 
        flash("Must specify first name","warning") 
        error=True
      if newm['last'] == "": 
        flash("Must specify last name","warning") 
        error=True
      if newm['email'] == "": 
        flash("Must assign a new/unque Member ID/Email","warning") 
        error=True
      if Member.query.filter(Member.member.ilike(newm['email'])).count() != 0:
        flash("Member ID/Email already in-use","warning") 
        error=True
      if error:
        return render_template('newmember.html',member=newm)

      if not newm['no_email']:
        if current_app.config['globalConfig'].DeployType.lower() == "production":
          try:
            users = google_admin.searchEmail(request.form['email'])
            if len(users) > 0:
              flash("Email address already exists in Google","warning")
              error=True
          except BaseException as e:
            flash("Error verifying gmail addr: "+str(e),"error")
            logger.error("Error verifying gmail addr: "+str(e))
            error=True

      if error:
        return render_template('newmember.html',member=newm)

      ## Everything is good - CREATE new member!
      if newm['no_email']:
        email=None
      else:
        email=newm['email']+'@makeitlabs.com'
      member = Member(member=newm['email'],email=newm['email']+'@makeitlabs.com',
          alt_email="billy@example.com",firstname=newm['first'],lastname=newm['last'],
          access_enabled=0,active=1,membership=newm['membership'],
          email_confirmed_at=datetime.utcnow())
      db.session.add(member)
      db.session.flush()
      s = Subscription.query.filter(Subscription.membership == newm['membership']).one()
      s.member_id = member.id
      authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_PAYMENT_LINKED.id,member_id=member.id,doneby=current_user.id,commit=0)
      if not newm['no_email']:
        ts = time.time()
        password = "%s-%d" % (newm['last'],ts - (len(newm['email']) * 314))
        if current_app.config['globalConfig'].DeployType.lower() != "production":
            flash("Skipping Google Create - Non Production","warning")
        else:
          try:
            user = google_admin.createUser(newm['first'],newm['last'],newm['email'],newm['alt_email'],password)
            google_admin.sendWelcomeEmail(user,password,newm['alt_email'])
          except BaseException as e:
            logger.error("Error create Google act: "+str(e))
            flash("Error create Google act: "+str(e),"warning")
            error=True

      if error:
        db.session.rollback()
        return render_template('newmember.html',member=newm)
      else:
        db.session.commit()
        flash("Created","success") 
      # TODO Create Google
        return redirect(url_for('members.member_show',id=newm['email']))

  if 'Assign' in request.form:
    linkmemberid = None
    if 'link_specific_member' in request.form:
      linkmemberid = request.form['link_specific_member']
    if 'do_sub' not in request.form:
      if linkmemberid:
        flash ("Choose a subscription to \"Assign To\" this member","warning")
      else:
        flash ("Designate a subscription as \"New Member\" or \"Assign To\" an existing account","warning")
      return redirect(url_for('payments.relate',member_id=linkmemberid))
    (action,membership) = request.form['do_sub'].split(":",1)
    if action == "assign"  and 'member_radio' not in request.form:
      flash ("You must (search for and select) a Member to Assign a subscription to","warning")
      return redirect(url_for('payments.relate'))

    if action == "assign":
      mem = Member.query.filter(Member.member == request.form['member_radio']).one()
      memsub = Subscription.query.filter(Subscription.member_id == mem.id).all()
      if len(memsub) != 0:
        flash ("Member already has a membership","warning")
      else:
        mem.membership=membership
        s = Subscription.query.filter(Subscription.membership == mem.membership).one()
        authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_PAYMENT_LINKED.id,member_id=mem.id,doneby=current_user.id,commit=0)
        s.member_id = mem.id
        db.session.commit()
        flash ("Assigning subscription to existing member","success")
    elif action == "create":
      s = Subscription.query.filter(Subscription.membership == membership).one()
      fn=""
      ln=""
      n=s.name.split(" ")
      if len(n)==2:
        fn=safestr(n[0]).title()
        ln=safestr(n[1]).title()
      elif len(n)==1:
        flash("Single name given - Please check and correct","warning")
        ln=safestr(n[0]).title()
      else:
        flash("Multi-part name given - Please check and correct","warning")
        fn=safestr(n[0]).title()
        ln=" ".join(n[1:])
      newm={
        'first':fn,
        'last':ln,
        'member':fn+"."+ln,
        'email':fn+"."+ln,
        'plan':s.plan,
        'rate_plan':s.rate_plan,
        'membership':s.membership,
        'alt_email':s.email
      }
      return render_template('newmember.html',member=newm)
    else:
      flash("No action specified","warning")
        
  if linkmemberid:
    return redirect(url_for('members.member_show',id=mem.member))
  return redirect(url_for('payments.relate'))

@blueprint.route('/google_acct_avail/<string:name>', methods = ['GET'])
@login_required
@roles_required(['Admin','Finance'])
def google_acct_avail(name):
  m = Member.query.filter(Member.member.ilike(name)).all()
  if len(m) > 0:
    return json_dump({'status':'error','message':'Member Exists'}), 200, {'Content-type': 'application/json'}

  try:
    users = google_admin.searchEmail(name)
  except BaseException as e:
    logger.error("Google email search failed: "+str(e))
    return json_dump({'status':'error','message':'Error checking Google'}), 200, {'Content-type': 'application/json'}
    
  if len(users) > 0:
    return json_dump({'status':"error","message":"Exists in Google"}), 200, {'Content-type': 'application/json'}
  #status must be "available" or "in-use"
  return json_dump({'status':"ok","message":"available"}), 200, {'Content-type': 'application/json'}

def register_pages(app):
	app.register_blueprint(blueprint)

