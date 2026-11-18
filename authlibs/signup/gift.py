#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs import accesslib
import stripe
import qrcode,io
from datetime import datetime,timedelta
from dateutil.relativedelta import relativedelta
from ..membership import createMissingMemberAccounts
import calendar
import json
import pickle
import re
import socket
import redis
import hashlib
import base64
from pytz import UTC
from flask import make_response
from .signup import addMember

blueprint = Blueprint("gift", __name__, template_folder='templates', static_folder="static",url_prefix="/gift")

# Purchase or Redeem Gift Memberships

def sanistring(str):
    if str is None:
        return ""
    return str.strip()


@blueprint.route('/gift_payment', methods=['GET','POST'])
def gift_payment():
    try:
        r = redis.Redis()
        debug = "gift_payment\n"
        for (k,v) in request.form.items():
            debug += f"Form Key: {k} Value {v}\n"
        for (k,v) in request.args.items():
            debug += f"Args Key: {k} Value: {v}\n"

        discounts=[]
        line_item = {
                    "price": "3mogift",
                    "quantity": 1,
                }

        recipname = ""
        if request.form.get("gift_to") is not None:
            recipname = request.form.get("gift_to")

        giftfrom = ""
        if request.form.get("gift_from") is not None:
            giftfrom = request.form.get("gift_from")

        customtext = ""
        if recipname != "":
            customtext = "Gift membership for "+recipname
        
        stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
        baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=request.form.get("email"),
            line_items=[ line_item ],
            mode="payment",
            custom_text={"submit":{"message":f"Enter YOUR information above. {customtext}"}},
            payment_intent_data={
                "metadata": {
                    "recipient":recipname,
                    "giftfrom":giftfrom
                    },
                "description": f"Gift Membership for {recipname}"
                },
            discounts = discounts,
            success_url=baseurl+url_for('gift.gift_postpay')+"?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=baseurl+url_for('gift.gift_failure')
        )
        logger.warning("FORM DATA: "+str(request.form.items()))
        logger.warning("SESSION INFO: "+str(session))
        logger.warning("Session ID: "+str(session['id']))


        sessiondata = {
                "gift_from":request.form.get("gift_from"),
                "phone":request.form.get("phone"),
                "email":request.form.get("email"),
                "gift_to":request.form.get("gift_to"),
                "to_email":request.form.get("to_email")
                }
                
        r.set("checkoutsession/"+session['id'],json.dumps(sessiondata))
        r.expire("checkoutsession/"+session['id'],3600)
    except BaseException as e:
        flash(f"Error: {e}",'danger')
        return redirect(url_for("gift.gift"))

    return redirect(session.url, code=303)

@blueprint.route('/success', methods=['GET','POST'])
def success():
    debug = "SUCCESS\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('debug.html',debug=debug)

@blueprint.route('/failure', methods=['GET','POST'])
def failure():
    debug = "FAILURE\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('debug.html',debug=debug)

@blueprint.route('/gift_failure', methods=['GET','POST'])
def gift_failure():
    debug = "GIFT FAILURE\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('debug.html',debug=debug)

@blueprint.route('/gift_postpay', methods=['GET','POST'])
def gift_postpay():
    # Just display the message. If we needed anything custom,
    # We could have used the session id w/ Redis

    opts={'isError': False}
    debug=""
    try:
        stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
        checkout_session_id = request.args.get('session_id')
        checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)
        r = redis.Redis()
        ses = r.get("checkoutsession/"+checkout_session['id'])
        if ses is None:
            debug += "No session data"
            return render_template('debug.html',"Session has expired")
        sessiondata = json.loads(ses)
        debug += "Session data: "+ses.decode('utf8')+"\n"
        opts['code'] = checkout_session['payment_intent']
        # Do we need this?!
        #opts['gift_to'] = sessiondata['gift_to']
        opts['email'] = sessiondata['email']
    except:
        opts['isError'] = True
    #debug+="Checkout Session:\n"+str(checkout_session)+"\n"
    return render_template('gift_post.html',debug=debug, **opts)

# Process user form to redeem a membership
@blueprint.route('/redeem_activate/<string:code>', methods=['GET','POST'])
@blueprint.route('/redeem_activate', methods=['POST','GET'])
def redeem_activate(code=None):

    debug="Redeem Activate\n"
    if code is None:
        code = request.form.get("code")

    if (code is None) or (code == "") or (not code.startswith("pi_")):
            flash ('Please specify a valid activation code',"danger")
            return redirect(url_for("gift.redeem"))

    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    debug += f"Redeem code: {code}\n"

    firstname = authutil.sanitize_name(request.form.get("firstname"))
    lastname = authutil.sanitize_name(request.form.get("lastname"))
    email = sanistring(request.form.get("email"))
    phone = sanistring(request.form.get("phone"))
    debug += "Name: {firstname} {lastname} Phone: {phone} Email: {email}\n"

    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if (re.match(pattern, email) is None):
        flash ('Please specify a valid email address',"danger")
        return redirect(url_for("gift.redeem",code=code))

    pattern = r"^\d\d\d-\d\d\d-\d\d\d\d$"
    if (re.match(pattern, phone) is None):
        flash ('Please specify a valid phone number with area code in the form of XXX-XXX-XXXX',"danger")
        return redirect(url_for("gift.redeem",code=code))

    if (email == "" ) or (firstname == "") or (lastname ==""):
        flash ('Please enter all fields',"danger")
        return redirect(url_for("gift.redeem",code=code))


    # Re-Verify that gift purchase is valid and has not been redeemed
    try:
        pi = stripe.PaymentIntent.retrieve(code)
        md = pi['metadata']
        debug += "\n\n"+str(md)

        if 'activated' in md:
            flash ('This gift membership has already been activated. if you believe you have received this message in error, please email info@makeitlabs.com for help.','danger')
            return redirect(url_for("gift.redeem"))

    except stripe.error.InvalidRequestError as e:
        flash ("The specified redemption code does not exist.  If you believe you have received this message in error, please email info@makeitlabs.com for help.",'danger')
        return redirect(url_for("gift.redeem"))

    except BaseException as e:
        flash (f"\nError getting code (2): {e} {type(e)}","danger")
        return redirect(url_for("gift.redeem"))

    fullname = f"{firstname} {lastname}"
    # Create new Customer
    try:
        customer = stripe.Customer.create(
          name=fullname,
          email=email,
          phone=phone,
          description=fullname
        )
    except BaseException as e:
        flash (f"\nError creating customer: {e}","danger")
        return redirect(url_for("gift.redeem"))

    # Create Subscription
    # We make gift recipients enter credit card - We probably SHOULD just use
    # checkout API instead, then do low-level creation on success of that
    try:
        three_months_from_now = datetime.now() + relativedelta(months=3, days=-1)
        cancel_timestamp = int(three_months_from_now.timestamp())
        sub = stripe.Subscription.create(
            customer=customer,
            cancel_at=cancel_timestamp,
            metadata= {
                      "emails": email,
                      "names": fullname
                },
            items = [
                {
                    "price": "hobbyist",
                    "discounts": [
                        {
                            "coupon":"3mogift",
                        }
                        ],
                    "metadata": {
                      "emails": email,
                      "names": fullname
              }
                    }
                ],
        )
    except BaseException as e:
        flash (f"\nError creating subscription: {e}","danger")
        return redirect(url_for("gift.redeem"))

    # TODO - Check that email is unique! Fail if not!!!!
    (s,mm) = addMember(sub,"hobbyist",firstname,lastname,email)

    db.session.commit()
    isTest = socket.gethostname()  == "staging"
    createMissingMemberAccounts([mm],isTest=isTest)
    debug += "isTest is {isTest}\n"

    # Mark gift purchase as Redeemed
    try:
        stripe.PaymentIntent.modify(
            code,
            metadata={"activated": f"SubID: {sub.id} for {firstname} {lastname}"},
        )
    except BaseException as e:
        logger.error(f"Could not mark Gift Purchase as activated: {e}")

    # Have Customer update Card on File
    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
    session = stripe.checkout.Session.create(
        customer = customer.id,
        payment_method_types=["card"],
        mode="setup",
        success_url=baseurl+url_for('gift.redeem_success')+"?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=baseurl+url_for("gift.redeem")
    )

    r = redis.Redis()
    sessiondata={'email':email}
    r.set("checkoutsession/"+session['id'],json.dumps(sessiondata))
    r.expire("checkoutsession/"+session['id'],3600)
    return redirect(session.url, code=303)

    #return render_template('complete.html',debug=debug,email=email,mtype="hobbyist")
    #return render_template('debug.html',debug=debug)

@blueprint.route('/redeem_success', methods=['GET','POST'])
def redeem_success():
    # Just display the message. If we needed anything custom,
    # We could have used the session id w/ Redis

    opts={'isError': False}
    debug=""
    try:
        stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
        checkout_session_id = request.args.get('session_id')
        checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)
        r = redis.Redis()
        ses = r.get("checkoutsession/"+checkout_session['id'])
        if ses is None:
            debug += "No session data"
            return render_template('debug.html',"Session has expired")
        sessiondata = json.loads(ses)
    except BaseException as e:
        print (f"REDEEM SUCCESS ERROR {e}")
    return render_template('redeem_success.html',debug=debug)

@blueprint.route("/redeem",methods=['POST','GET'])
@blueprint.route("/redeem/<string:code>",methods=['GET','POST'])
def redeem(code=None):
    if 'code' in request.form:
        code = request.form.get('code')
    code = request.args.get('code',code)
    if code is None or code == "":
        flash("Enter Redeem Code")
        return render_template('redeem_code.html')
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    debug=f"code = {code}"
    try:
        pi = stripe.PaymentIntent.retrieve(code)
        md = pi['metadata']
        recip = "New Member"
        if 'recipient' in md:
            recip = md['recipient']
        debug += "\n\n"+str(md)

        if 'activated' in md:
            flash ('This gift membership has already been activated. if you believe you have received this message in error, please email info@makeitlabs.com for help.','danger')
            return redirect(url_for("gift.redeem"))

        return render_template('redeem.html',gift_to=recip,debug=debug,code=code)
    except stripe.error.InvalidRequestError as e:
        flash ("The specified redemption code does not exist.  If you believe you have received this message in error, please email info@makeitlabs.com for help.",'danger')
        return redirect(url_for("gift.redeem"))

    except BaseException as e:
        debug += f"\nError getting code: {e} {type(e)}"

    debug += "\n\nPlease email info@makeitlabs.com for more assitance"
    return render_template('debug.html',debug=debug)

@blueprint.route("/qrcode/<string:code>")
def qr(code):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
    qr.add_data(baseurl+url_for("gift.redeem",code=code))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    byte_data = buffer.getvalue()
    response = make_response(byte_data)
    response.headers['Content-Type'] = 'image/png'
    return response

# First entry: Purchase Gift Membership
@blueprint.route('/', methods=['GET','POST'])
def gift():

    debug = "DEBUG\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('gift.html',debug=debug)


def register_pages(app):
	app.register_blueprint(blueprint)
