#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs import accesslib
import stripe
import qrcode,io
from datetime import datetime,timedelta
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
import sqlalchemy.exc

blueprint = Blueprint("signup", __name__, template_folder='templates', static_folder="static",url_prefix="/signup")

# New Mebership Signup - Self Service Portal

# Takes Stripe Subscription Object and subcription id
# Returns subscription and member object
def addMember(sub,plantype,firstname,lastname,email):
    name= firstname+" "+lastname
    membership = "stripe:"+name.replace(" ",".")+":"+email
    expires = datetime.utcfromtimestamp(sub['current_period_end'])
    created = datetime.utcfromtimestamp(sub['created'])
    updated = datetime.utcnow()

    # Add Subscription to Database
    s=Subscription(membership=membership)
    s.paysystem = "stripe"
    s.subid = sub.id
    s.customerid = sub['customer']
    s.name = (firstname+" "+lastname)
    s.email = email
    s.plan = plantype
    s.rate_plan = sub['plan']['id']
    s.expires_date = expires
    s.created_date = created
    s.updated_date = updated
    s.membership = membership
    s.checked_date = datetime.utcnow()
    s.active = 'true'

    # Add Member to Database
    mm = Member()
    mm.member = (firstname+" "+lastname).replace(" ",".")
    mm.firstname = firstname
    mm.lastname = lastname
    mm.alt_email = email
    mm.active = 'true'
    mm.plan = plantype
    mm.stripe_name = firstname+" "+lastname
    mm.time_created = created
    mm.time_updated = updated
    mm.email_confirmed_at = datetime.now()

    grp = None
    if hasattr(sub, 'metadata') and sub.metadata and 'group' in sub.metadata and sub.metadata['group']:
        grp = sub.metadata['group'].strip()
    elif isinstance(sub, dict) and 'metadata' in sub and sub['metadata'] and 'group' in sub['metadata'] and sub['metadata']['group']:
        grp = sub['metadata']['group'].strip()
    elif isinstance(sub, dict) and 'group' in sub and sub['group']:
        grp = str(sub['group']).strip()
    if grp == "": grp = None

    if grp:
        s.group = grp
        mm.group = grp

    db.session.add(mm)
    db.session.flush() # BKG UNIQUE CONTRAINTS FAILED if duplicate member name!

    logger.debug("Adding new member %s for subscription %s MemberID %s" % (name, sub.id,mm.id))
    s.member_id=mm.id
    db.session.add(s)
    db.session.add(Logs(member_id=mm.id,event_type=eventtypes.RATTBE_LOGEVENT_CONFIG_NEW_MEMBER_PAYSYS.id))
    return (s,mm)

def linkExistingMember(sub, plantype, firstname, lastname, email):
    """
    Called when addMember() fails with a UNIQUE constraint on members.member,
    meaning this person already has a member record.  Instead of failing, we
    find that existing Member row and link/update the new Stripe subscription
    to it, effectively reactivating the membership.
    """
    membername = (firstname + " " + lastname).replace(" ", ".")
    mm = Member.query.filter(Member.member == membername).first()
    if mm is None:
        raise ValueError(f"Duplicate insert signalled but member not found: {membername}")

    expires = datetime.utcfromtimestamp(sub['current_period_end'])
    created = datetime.utcfromtimestamp(sub['created'])
    updated = datetime.utcnow()

    # Find the existing Subscription row for this member
    s = Subscription.query.filter(Subscription.member_id == mm.id).first()
    if s is None:
        # No subscription row yet — create one fresh
        membership = "stripe:" + membername + ":" + email
        s = Subscription(membership=membership)
        s.member_id = mm.id
        db.session.add(s)

    # Update it with the new Stripe subscription details
    s.paysystem    = "stripe"
    s.subid        = sub.id
    s.customerid   = sub['customer']
    s.name         = firstname + " " + lastname
    s.email        = email
    s.plan         = plantype
    s.rate_plan    = sub['plan']['id']
    s.expires_date = expires
    s.created_date = created
    s.updated_date = updated
    s.checked_date = datetime.utcnow()
    s.active       = 'true'

    # Update the member's last-updated timestamp.
    # NOTE: Do NOT touch mm.active — it is a computed status string (e.g. 'Active',
    # 'Grace Period', 'Recent Expire') managed by the Stripe sync process, not a
    # flag we should set manually here.
    mm.time_updated = updated

    grp = None
    if hasattr(sub, 'metadata') and sub.metadata and 'group' in sub.metadata and sub.metadata['group']:
        grp = sub.metadata['group'].strip()
    elif isinstance(sub, dict) and 'metadata' in sub and sub['metadata'] and 'group' in sub['metadata'] and sub['metadata']['group']:
        grp = sub['metadata']['group'].strip()
    elif isinstance(sub, dict) and 'group' in sub and sub['group']:
        grp = str(sub['group']).strip()
    if grp == "": grp = None

    if grp:
        s.group = grp
        if not mm.group or mm.group.strip() == '':
            mm.group = grp

    db.session.add(Logs(member_id=mm.id,
                        event_type=eventtypes.RATTBE_LOGEVENT_MEMBER_REACTIVATED.id))
    db.session.add(Logs(member_id=mm.id,
                        event_type=eventtypes.RATTBE_LOGEVENT_CONFIG_SUB_ACTIVATED_PAYSYS.id,
                        message="Subscription reactivated via signup portal"))
    return (s, mm)

@blueprint.route('/howdiduhear', methods=['GET','POST'])
def howdiduhear():
    return render_template('wherediduhear.html',where=where,what=what,stuff=stuff,iam=iam)

@blueprint.route('/postpay', methods=['GET','POST'])
def postpay():
    where = [
                {'name':'holidaystroll', 'text':"Nashua Holiday Stroll" },
                {'name':'lksr', 'text':"Lowell Kinetic Sculpture Race" },
                {'name':'makeitfest', 'text':"MakeIt Fest" },
                {'name':'member', 'text':"From another Member" },
                {'name':'social', 'text':"Social Media" },
            ]
    what = [
                {'name':'art', 'text':"Art (Painting, Drawing, Airbrushing, etc." },
                {'name':'blacksmithing', 'text':"Blacksmithing" },
                {'name':'jewelry', 'text':"Jewelry Making and Soft Metals" },
                {'name':'glasswork', 'text':"Glasswork" },
                {'name':'photography', 'text':"Photography & Darkroom" },
                {'name':'pottery', 'text':"Pottery" },
                {'name':'woodworking', 'text':"Woodworking (General, turning & routing)"},
                {'name':'auto', 'text':"Automotive" },
                {'name':'welding', 'text':"Welding" },
                {'name':'machining', 'text':"Machining and Metalwork" },
                {'name':'laser', 'text':"Laser Cutting (wood, metal, acrylic, etc.)" },
                {'name':'ham', 'text':"Radio Operator (Ham)"},
                {'name':'production', 'text':"Procducer (Video, Audio, Podcast, etc)."},
                {'name':'3dprinting', 'text':"3d Printing" },
                {'name':'design', 'text':"CAD & other software tools for physical design" },
                {'name':'software', 'text':"Software (Writing software, web design, etc.)"},
                {'name':'electronics', 'text':"Electronics (Hardware, PCB design, Arduino, etc.)"}
            ]
    stuff = [
                {'name':'learning', 'text':"Taking Classes and Workshops" },
                {'name':'community', 'text':"Community and social events" },
                {'name':'collaberation', 'text':"Partipating in group projects" },
                {'name':'volunteer', 'text':"Volunteering & helping in operation of our lab" },
                {'name':'making', 'text':"Making stuff" },
                {'name':'fixing', 'text':"Fixing/Repairing stuff" },
                {'name':'teaching', 'text':"Teaching Classes and Workshops" },
            ]
    iam = [
                {'name':'engineer', 'text':"Engineer" },
                {'name':'artist', 'text':"Artist" },
                {'name':'hacker', 'text':"Hacker" },
                {'name':'teacher', 'text':"Teacher" },
                {'name':'student', 'text':"Student (lifelong)" },
                {'name':'builder', 'text':"Builder" },
                {'name':'fixer', 'text':"Fixer" },
                {'name':'handson', 'text':"Hands-On" },
                {'name':'madscientist', 'text':"Scientist (Mad)" },
                {'name':'othercientist', 'text':"Scientist (Other)" },
            ]

    debug = "POSTPAY\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    checkout_session_id = request.args.get('session_id')
    checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)
    
    debug += "\n\n"+str(dir(checkout_session))
    debug += "\n\n"+str(dict(checkout_session))

    debug += f"\n\nid: {checkout_session['id']}\n"
    debug += f"object: {checkout_session['object']}\n"
    debug += f"subscription: {checkout_session['subscription']}\n"

    r = redis.Redis()
    ses = r.get("checkoutsession/"+checkout_session['id'])
    sessiondata = None
    if ses is not None:
        try:
            sessiondata = json.loads(ses.decode('utf8') if isinstance(ses, bytes) else ses)
            debug += "Session data: " + (ses.decode('utf8') if isinstance(ses, bytes) else str(ses)) + "\n"
        except Exception as e:
            debug += f"Failed to parse session data: {e}\n"
    else:
        debug += "No session data in Redis\n"
    
    # Now we have a real Stripe subscription, and the data the user registered with.
    # Put it all together.

    sub = stripe.Subscription.retrieve(checkout_session['subscription'])
    debug += "\n\nSubscription:\n\n"
    debug += str(sub)

    # Reconstruct sessiondata if Redis session expired or was missing
    if sessiondata is None:
        sessiondata = {}
        meta_names = sub.get('metadata', {}).get('names', '')
        meta_emails = sub.get('metadata', {}).get('emails', '')
        names_list = [n.strip() for n in meta_names.split(',')] if meta_names else []
        emails_list = [e.strip() for e in meta_emails.split(',')] if meta_emails else []

        if names_list:
            parts = names_list[0].split(' ', 1)
            sessiondata['firstname'] = parts[0]
            sessiondata['lastname'] = parts[1] if len(parts) > 1 else ''
        else:
            sessiondata['firstname'] = 'Member'
            sessiondata['lastname'] = ''

        cust_details = checkout_session.get('customer_details') or {}
        sessiondata['email'] = emails_list[0] if emails_list else (cust_details.get('email') or '')
        sessiondata['phone'] = cust_details.get('phone') or ''

        plan_id = sub.get('plan', {}).get('id', 'hobbyist')
        sessiondata['mtype'] = plan_id

        if len(names_list) > 1 and len(emails_list) > 1:
            sessiondata['mtype'] = 'produo'
            parts2 = names_list[1].split(' ', 1)
            sessiondata['firstname2'] = parts2[0]
            sessiondata['lastname2'] = parts2[1] if len(parts2) > 1 else ''
            sessiondata['email2'] = emails_list[1]
            sessiondata['phone2'] = ''

    # Determine customer's full name from subscription metadata or session data
    cust_name = sub.get('metadata', {}).get('names')
    if not cust_name and sessiondata:
        cust_name = f"{sessiondata.get('firstname', '')} {sessiondata.get('lastname', '')}".strip()
        if sessiondata.get('mtype') == 'produo' and sessiondata.get('firstname2'):
            cust_name += f", {sessiondata.get('firstname2', '')} {sessiondata.get('lastname2', '')}".strip()

    # Also set the Customer Name and Description to their name in Stripe!
    if cust_name and sub.get('customer'):
        cust_update = {
            'name': cust_name,
            'description': cust_name
        }
        if sessiondata.get('phone'):
            cust_update['phone'] = sessiondata['phone']
        if sessiondata.get('email'):
            cust_update['email'] = sessiondata['email']

        try:
            stripe.Customer.modify(sub['customer'], **cust_update)
            debug += f"\n\nUpdated Customer {sub['customer']} with {cust_update}\n"
            logger.info(f"Signup: updated customer {sub['customer']} with {cust_update}")
        except BaseException as e:
            debug += f"\n\nError updating customer name: {e}\n"
            logger.error(f"Signup: failed to update customer name for {sub['customer']}: {e}")

    # Set the payment method from this subscription as the customer's default
    # invoice payment method. Without this, the card is attached but not the
    # default, which causes vending/consumable charges to fail.
    try:
        pm = sub.get('default_payment_method')
        if pm is None:
            # Fallback 1: look at the latest invoice's payment intent
            try:
                latest_invoice = stripe.Invoice.retrieve(sub['latest_invoice'])
                if latest_invoice.get('payment_intent'):
                    pi = stripe.PaymentIntent.retrieve(latest_invoice['payment_intent'])
                    pm = pi.get('payment_method')
            except BaseException as e2:
                debug += f"\n\nInvoice/PI fallback failed: {e2}\n"
        if pm is None:
            # Fallback 2: use most recently attached card (same as fix script)
            try:
                attached_pms = stripe.PaymentMethod.list(customer=sub['customer'], type="card")
                if attached_pms and attached_pms.get('data'):
                    pm = attached_pms['data'][0].id
                    debug += f"\n\nUsing attached card as fallback: {pm}\n"
            except BaseException as e3:
                debug += f"\n\nAttached PM fallback failed: {e3}\n"
        if pm:
            stripe.Customer.modify(sub['customer'], invoice_settings={'default_payment_method': pm})
            debug += f"\n\nSet default payment method: {pm}\n"
            logger.info(f"Signup: set default payment method {pm} for customer {sub['customer']}")
        else:
            debug += "\n\nWARNING: No payment method found to set as default\n"
            logger.warning(f"Signup: no payment method found for customer {sub['customer']}")
    except BaseException as e:
        debug += f"\n\nError setting default payment method: {e}\n"
        logger.error(f"Signup: failed to set default payment method for customer {sub['customer']}: {e}")

    # Add subscription data into Redis for quick reference
    sessiondata['subscription'] = checkout_session['subscription']

    r.set("checkoutsession/"+checkout_session['id'], json.dumps(sessiondata))
    r.expire("checkoutsession/"+checkout_session['id'], 86400)

    plan = sub['plan']['id']
    planname = "hobbyist"
    if plan in ['hobbyist']:
        plantype = "hobbyist"
    elif plan in ['free','pro','produo','board','resourcemgr']:
        plantype = 'pro'
    elif "group_pro" in plan:
        plantype = 'pro'
    elif "group" in plan:
        plantype = 'hobbyist'

    isTest = socket.gethostname()  == "staging"
    isError = False
    isDuplicate = False
    try:
        (s,mm) = addMember(sub,plantype,sessiondata['firstname'],sessiondata['lastname'],
                sessiondata['email'])
        createMissingMemberAccounts([mm],isTest=isTest)

        if (plan == "produo"):
            (s,mm) = addMember(sub,plantype,sessiondata['firstname2'],sessiondata['lastname2'],
                sessiondata['email2'])
            createMissingMemberAccounts([mm],isTest=isTest)
        db.session.commit()
    except sqlalchemy.exc.IntegrityError as e:
        # Member record already exists — roll back the failed insert and
        # instead link the new Stripe subscription to the existing member.
        db.session.rollback()
        print(f"Signup: duplicate member detected for {sessiondata['email']}, attempting to link subscription")
        try:
            (s, mm) = linkExistingMember(sub, plantype, sessiondata['firstname'],
                                         sessiondata['lastname'], sessiondata['email'])
            db.session.commit()
            authutil.kick_backend()
            isDuplicate = True   # reactivation succeeded
        except BaseException as e2:
            db.session.rollback()
            print(f"Signup: link also failed for {sessiondata['email']}: {e2}\n")
            isError = True
    except BaseException as e:
        db.session.rollback()
        print(f"Signup error: {sessiondata['email']}: {e}\n")
        isError = True

    return render_template('complete.html',debug=debug,email=sessiondata['email'],
            mtype=sessiondata['mtype'],isError=isError,isDuplicate=isDuplicate,
            where=where,what=what,stuff=stuff,iam=iam)

@blueprint.route('/survey',methods=['POST'])
def survey():

    results = datetime.now().isoformat()+": "
    for x in request.form:
        if x.startswith("other_"):
            s = request.form.get(x).replace("\"","'")
            s = s.replace(" ","_")
            results += f"{x}: \"{s}\" "
        else:
            results += f"{x} "

    with open("survey.txt","a") as fd:
        fd.write(results+"\n")
    return render_template('survey_complete.html',results=results)

@blueprint.route('/payment', methods=['GET','POST'])
def payment():
    r = redis.Redis()
    debug = "payment\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    #return render_template('debug.html',debug=debug)

    mtype = request.form.get("membershipType")

    if not mtype:
        flash("Please select a membership type")
        return redirect(url_for("signup.signup"))

    if (
            (request.form.get("firstname", "").strip() == "") or
            (request.form.get("lastname", "").strip() == "") or
            (request.form.get("email", "").strip() == "") or
            (request.form.get("phone", "").strip() == "")):
        flash("Please make sure ALL fields are complete")
        return redirect(url_for("signup.signup"))

    if (mtype == "produo"):
        if (
                (request.form.get("firstname2", "").strip() == "") or
                (request.form.get("lastname2", "").strip() == "") or
                (request.form.get("email2", "").strip() == "") or
                (request.form.get("phone2", "").strip() == "")):
            flash("Please make sure ALL fields are complete")
            return redirect(url_for("signup.signup"))

    discounts=[]
    line_item = {
                "price": mtype,  # or "hobbiest"
                "quantity": 1,
            }
    if mtype == "militarypro":
        line_item['price'] = "pro"
        discounts = [
                {
                    "coupon": "MILITARYPRO"
                    }
                ]
    
    # Build metadata for subscription
    names = request.form.get("firstname")+" "+request.form.get("lastname")
    emails = request.form.get("email")
    if mtype == "produo":
        names += ", "+request.form.get("firstname2")+" "+request.form.get("lastname2")
        emails += ", "+request.form.get("email2")
    
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        customer_email=request.form.get("email"),
        line_items=[ line_item ],
        mode="subscription",
        discounts = discounts,
        subscription_data={
            "metadata": {
                "emails": emails,
                "names": names
            }
        },
        success_url=baseurl+url_for('signup.postpay')+"?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=baseurl+url_for('signup.failure')
    )

    sessiondata = {
            "firstname":request.form.get("firstname"),
            "lastname":request.form.get("lastname"),
            "phone":request.form.get("phone"),
            "email":request.form.get("email"),
            "mtype":mtype
            }
    if (mtype == "produo"):
        sessiondata["firstname2"] = request.form.get("firstname2")
        sessiondata["lastname2"] = request.form.get("lastname2")
        sessiondata["phone2"] = request.form.get("phone2")
        sessiondata["email2"] = request.form.get("email2")
            
    r.set("checkoutsession/"+session['id'], json.dumps(sessiondata))
    r.expire("checkoutsession/"+session['id'], 86400)
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

@blueprint.route("/qrcode/<string:code>")
def qr(code):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
    qr.add_data(baseurl+url_for("signup.redeem",code=code))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    byte_data = buffer.getvalue()
    response = make_response(byte_data)
    response.headers['Content-Type'] = 'image/png'
    return response

@blueprint.route("/start_payment_session")
def start_payment_session():
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        metadata = {
            "firstname":request.form.get('firstname'),
            "lastname":request.form.get('lastname'),
            },
        custom_fields = [
                {
                    "key":"XXfirstname",
                    "label":"XXfirstname",
                    "type":"text"
                },
                {
                    "key":"lll",
                    "label":"lll",
                    "type":"text"
                }
            ],
        line_items=[
            {
                "price": "pro",  # or "hobbiest"
                "quantity": 1,
            }
        ],
        mode="subscription",
        success_url="success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=baseurl+url_for("signup.payupdate")
    )
    return redirect(checkout_session.url, code=303)
    #return jsonify({"session_id": session.id})


@blueprint.route("/modify")
def modify():
    url = current_app.config['globalConfig'].Config.get('Stripe','modify_billing_url')
    return redirect(url, code=303)

@blueprint.route('/', methods=['GET','POST'])
def signup():

    debug = "DEBUG\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('signup.html',debug=debug)

def register_pages(app):
	app.register_blueprint(blueprint)
