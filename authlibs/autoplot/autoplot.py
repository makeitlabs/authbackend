# vim:shiftwidth=2


from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago
from ..google_admin import genericEmailSender

#import .crunchauto
from .crunchauto import crunch_calendar,do_payment

blueprint = Blueprint("autoplot", __name__, template_folder='templates', static_folder="static",url_prefix="/autoplot")


def sendemails(subject="MIL Lease Update",text="(No Body)"):
  # Find Lease Managers
  lms = Member.query.join(UserRoles,(Member.id == UserRoles.member_id))
  lms = lms.join(Role,(Role.id == UserRoles.role_id) & (Role.name=="LeaseMgr"))
  for x in lms.all():
    #print (x.member,x.email)
    try:
      genericEmailSender("info@makeitlabs.com",x.email,subject,text)
    except BaseException as e:
      logger.error("Lease Update Email Fail: "+str(e))

# This does it all from GUI, CLI and API
def autoplot_logic(rundate=None,process_payment=False,process_invoice=False,debug=False,noemail=False):
  price = current_app.config['globalConfig'].Config.get("autoplot","stripe_item")
  if rundate is None:
    rundate = datetime.now().strftime("%Y-%m-%d")
  #print "RUNDATE EFFECTIVE",rundate
  (errors,warnings,debug,data,billables) = crunch_calendar(rundate)
  if (len(errors) == 0) and len(billables) ==1:
      mem = Member.query.filter(func.lower(Member.member)==func.lower(billables[0]['member'].replace("@makeitlabs.com",''))).one_or_none()
      if mem:
          #print (billables[0]['member'])
          #print (mem.stripe_name)
          sub = Subscription.query.filter(Subscription.member_id == mem.id).one_or_none()
          if sub:
              data['Stripe ID']=sub.customerid
              data['Plan']=sub.plan
              data['Active']=sub.active
              if not data['Active']:
                  errors.append("Membership Inactive")
              # if data['Plan'] != "pro": errors.append("Not a pro member")
          else:
              errors.append("Subscription Not Found")
      else:
          errors.append("Member not found")
  # If we found an error  in membership or subscriptionm chekcs
  if len(errors) > 0:
      data['Decision']='error'

  data['pay_status'] = 'unbilled'
  if data['Decision'] == 'bill':
      # Check log
      #run billing code
      # log even
      #
      logs = Logs.query.filter((Logs.member_id == mem.id) & (Logs.event_type == eventtypes.RATTBE_LOGEVENT_MEMBER_LEASE_CHARGE.id) & (Logs.message== data['lease-id'])).all()
      if (len(logs) > 0):
        data['pay_status']='already_paid'
      elif process_invoice:
        dopay = False
        (pay_errors,pay_warnings,pay_debug,pay_status) = do_payment(data['Stripe ID'],price,data['lease-id'],data['title'],pay=process_payment)
        if len(pay_errors) >0: errors += ['PAYMENT',]
        errors += pay_errors
        if len(pay_warnings) >0: warnings += ['PAYMENT',]
        warnings += pay_warnings
        if len(pay_debug) >0: debug += ['PAYMENT',]
        debug += pay_debug
        data['pay_status']=pay_status
        if pay_status == 'paid' or pay_status == 'already_paid_stripe':
          #print "CURRENT_APP",type(current_app)
          #print "CURRENT_APP",current_app.extensions
          authutil.log(eventtypes.RATTBE_LOGEVENT_MEMBER_LEASE_CHARGE.id,member_id=mem.id,message=data['lease-id'],commit=0)
          db.session.commit()
  # Send Emails

  if data['Decision'] == 'error':
      subject="(!!) Auto Lease Payment ERRORS"
  elif data['pay_status'] == 'paid':
    subject = "Auto Plot Lease PAYMENT"
  else:
    subject = "Auto Plot Lease status"
  if len(warnings) > 0:
      subject+=" - WARNINGS!"
  text = ""
  for x in data:
    text += "{0}: {1}\n".format(x,data[x])
  if len(errors) >0:
    text += "\nErrors:"
    for x in errors:
      text += x+"\n"
  if len(warnings) >0:
    text += "\nWarnings:"
    for x in warnings:
      text += x+"\n"
  if len(debug) >0:
    text += "\nDebug:"
    for x in debug:
      text += x+"\n"
  sendemails(subject,text)
  #print "SUBJECT:",subject
  #print "TEXT:"
  #print text
  return (errors,warnings,debug,data,billables) 



@blueprint.route('/', methods=['GET','POST'])
@roles_required(['Admin','Finance','LeaseMgr'])
@login_required
def autoplot():
    """(Controller) Display Nodes and controls"""
    process_invoice =  'invoice' in request.form
    process_payment = 'pay' in request.form
    rundate = datetime.now().strftime("%Y-%m-%d")

    if 'Process' in request.form and 'datepicker' in request.form:
        rundate=request.form['datepicker']
        (errors,warnings,debug,data,billables) = autoplot_logic(rundate=rundate,process_payment=process_payment,process_invoice=process_invoice)
        return render_template('autoplot.html',defdate=rundate,errors=errors,warnings=warnings,debug=debug,data=data,billables=billables)
    # Default
    return render_template('autoplot.html',data=None,defdate=rundate)

def cli_autoplot(cmd,**kwargs):
    print ("AUTOPLOT",cmd)
    rundate=None
    if len(cmd)  >=2:
        rundate=cmd[1]
    (errors,warnings,debug,data,billables) = autoplot_logic(rundate=rundate)
    print ("**ERRORS")
    print (errors)
    print ("**WARNINGS")
    print (warnings)
    print ("**DEBUG")
    print (debug)
    print ("**DATA")
    print (data)
    print ("**BILLABLES")
    print (billables)


def autoplot_api():
  logger.warning("Autoplot Payment Cron")
  (errors,warnings,debug,data,billables) = autoplot_logic()
  if len(errors)>0:
    logger.warning("Weekly notice CRON ERROR")
    return json_dump({'status':'error'}, 401, {'Content-type': 'application/json'})
  else:
    logger.info("Weekly notice CRON finished")
    return json_dump({'status':'ok'}, 200, {'Content-type': 'application/json'})


def register_pages(app):
	app.register_blueprint(blueprint)

0
