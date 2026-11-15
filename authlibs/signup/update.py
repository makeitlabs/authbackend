#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs import accesslib
import stripe
import qrcode,io
from datetime import datetime,timedelta
from ..google_admin import genericEmailSender
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

blueprint = Blueprint("membershipupdate", __name__, template_folder='templates', static_folder="static",url_prefix="/membershipupdate")

def reactivate_subscription(customer, custid, subid, debug=""):
    """Reactivate a canceled subscription using the existing card on file."""
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    
    # Find the most recent ended subscription to get the plan details
    ss = stripe.Subscription.list(customer=custid, status="ended")
    recent = None
    mostrecent = None
    for s in ss['data']:
        if s.ended_at is not None and (recent is None or s.ended_at > recent):
            recent = s.ended_at
            mostrecent = s
        if s.canceled_at is not None and (recent is None or s.canceled_at > recent):
            recent = s.canceled_at
            mostrecent = s
    
    if mostrecent is None:
        return render_template('message.html', title="Error",
            message="Could not find a previous subscription to reactivate. Please contact support.")
    
    try:
        sub = stripe.Subscription.create(
            customer=custid,
            metadata=mostrecent['metadata'],
            description="Membership renewal",
            collection_method="charge_automatically",
            items=[
                {
                    "price": mostrecent.plan.id,
                }
            ],
        )
        # Ensure customer name and description are set in Stripe
        if 'names' in mostrecent.get('metadata', {}):
            try:
                stripe.Customer.modify(custid, name=mostrecent['metadata']['names'], description=mostrecent['metadata']['names'])
            except BaseException as ce:
                logger.warning(f"Reactivate: error updating customer name/desc for {custid}: {ce}")
        # Update local database
        fixMemberSubscription(sub)
        return render_template('message.html', title="Membership Reactivated",
            message="Your membership has been successfully reactivated!")
    except BaseException as e:
        return render_template('message.html', title="Error",
            message=f"An error occurred while reactivating your subscription: {e}")

# This is the one that will actually do something, that you will
# Get to only after receiving the link from the "fix" page, below
@blueprint.route('/fix2/<string:digest>/<int:now>/<string:email>', methods=['GET','POST'])
def fix2(digest,now,email):
    debug=f"{digest}\n{now}\n{email}"
    message=""

    # Verify digest
    secret_key =  current_app.config['globalConfig'].Config.get('General','SecretKey')
    sha = hashlib.sha256()
    sha.update(secret_key.encode('utf-8'))
    sha.update(email.encode('utf-8'))
    sha.update(now.to_bytes(8,byteorder="big"))

    calc_digest = base64.urlsafe_b64encode(sha.digest()).decode()

    if (calc_digest != digest):
        return render_template('message.html',title="Update or Reactivate Membership",message="Invalid Link")

    currenttime = int(datetime.utcnow().timestamp())
    if ((now+3600) < currenttime):
        return render_template('message.html',title="Update or Reactivate Membership",message="Link has expired. Please try again.")

    # See if we can find a valid membership
    members = Member.query.filter(
        or_(
            func.lower(Member.alt_email) == func.lower(email),
            func.lower(Member.email) == func.lower(email)
        )
    ).all()
    debug += str(members)
    debug += "\n\n"

    textmsg=""
    custids=[]
    subids=[]
    active="false"
    plan = None
    rateplan = None
    if len(members)==0:
        return render_template('message.html',title="Update or Reactivate Membership",message="No membership found for that email address")

    fullname=""
    for m in members:
        fullname = m.member.replace("."," ")
        for s in Subscription.query.filter(Subscription.member_id == m.id).all():
            if s.active == "true":
                active = s.active
                plan = s.plan
                rateplan = s.rate_plan
                if s.subid not in subids: subids.append(s.subid)
                if s.customerid not in custids: custids.append(s.customerid)

    if len(subids)!=1:
        return render_template('message.html',message="Multiple subscriptions exist. Please email for assistance.")
    if len(custids)!=1:
        return render_template('message.html',message="Multiple customer records exist. Please email for assistance.")

    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    stripe.api_version = '2020-08-27'

    c = stripe.Customer.retrieve(custids[0])
    default_pm = c['invoice_settings']['default_payment_method']
    has_card = default_pm is not None
    card_last4 = None
    if has_card:
        try:
            pm = stripe.PaymentMethod.retrieve(default_pm)
            if pm.card:
                card_last4 = pm.card.last4
        except:
            pass
    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')

    # Check for action parameter
    action = request.args.get('action')

    # Handle specific actions
    if action == 'updatecc':
        # Redirect to Stripe to update credit card
        session = stripe.checkout.Session.create(
            customer = c,
            payment_method_types=["card"],
            mode="setup",
            success_url=baseurl+url_for('membershipupdate.fix_postpay')+"?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=baseurl+url_for("membershipupdate.payupdate")
        )
        return redirect(session.url, code=303)

    if action == 'cancel':
        # Cancel the active subscription
        ss = stripe.Subscription.list(customer=custids[0])
        if len(ss['data']) > 0:
            try:
                stripe.Subscription.delete(ss['data'][0].id)
                return render_template('message.html', title="Membership Canceled",
                    message="Your membership has been canceled. You will retain access until the end of your current billing period.")
            except BaseException as e:
                return render_template('message.html', title="Error",
                    message=f"An error occurred while canceling your subscription: {e}")
        else:
            return render_template('message.html', title="No Active Subscription",
                message="No active subscription was found to cancel.")

    if action == 'reactivate':
        # Reactivate with existing card on file
        return reactivate_subscription(c, custids[0], subids[0], debug)

    if action == 'reactivate_newcard':
        # Update card first, then reactivate (handled in fix_postpay)
        session = stripe.checkout.Session.create(
            customer = c,
            payment_method_types=["card"],
            mode="setup",
            success_url=baseurl+url_for('membershipupdate.fix_postpay')+"?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=baseurl+url_for("membershipupdate.payupdate")
        )
        return redirect(session.url, code=303)

    # No action specified - show options based on membership status
    ss = stripe.Subscription.list(customer=custids[0])
    options = []

    if len(ss['data']) > 0:
        # Active subscription exists
        options.append({
            'label': 'Update Credit Card on File',
            'url': url_for('membershipupdate.fix2', digest=digest, now=now, email=email, action='updatecc'),
            'confirm': False
        })
        options.append({
            'label': 'Cancel Membership',
            'url': url_for('membershipupdate.fix2', digest=digest, now=now, email=email, action='cancel'),
            'confirm': True
        })
        message = "Your membership is currently active."
    else:
        # No active subscription - membership has been canceled
        message = "Your membership is currently inactive."
        if has_card:
            card_label = f'Reactivate with Existing Card (ending in {card_last4})' if card_last4 else 'Reactivate with Existing Card on File'
            options.append({
                'label': card_label,
                'url': url_for('membershipupdate.fix2', digest=digest, now=now, email=email, action='reactivate'),
                'confirm': True
            })
            options.append({
                'label': 'Update Card and Reactivate',
                'url': url_for('membershipupdate.fix2', digest=digest, now=now, email=email, action='reactivate_newcard'),
                'confirm': False
            })
        else:
            options.append({
                'label': 'Add Credit Card and Reactivate',
                'url': url_for('membershipupdate.fix2', digest=digest, now=now, email=email, action='reactivate_newcard'),
                'confirm': False
            })

    return render_template('fix2_confirm.html', fullname=fullname, email=email, options=options, message=message, debug=debug if current_app.config['globalConfig'].Config.get('General','Debug').lower() == 'true' else None)


@blueprint.route('/', methods=['GET'])
def payupdate():
    return render_template('payupdate.html')


# This doesn't do anything execpt send you a link
@blueprint.route('/fix', methods=['GET','POST'])
def fix():

    isDebug =  current_app.config['globalConfig'].Config.get('General','Debug').lower() == "true"
    debug = "FIX\n"
    emailtext = ""
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    if 'email' not in request.form:
        debug += "No email address specified\n"
        return render_template('message.html',message="No email address specified")
    email = request.form['email'].strip()
    members = Member.query.filter(
        or_(
            func.lower(Member.alt_email) == func.lower(email),
            func.lower(Member.email) == func.lower(email)
        )
    ).all()
    debug += str(members)

    if len(members)==0:
        emailtext="No membership with that email was found.\n"
    elif len(members)>1:
        emailtext="Multiple memberships were found with that email address. Please specify which you are trying to reactivate.\n"
    else:
        altemail = members[0].alt_email
        email = members[0].email
        emailtext=f"Membership found: {email} {altemail}\n"

        now = int(datetime.utcnow().timestamp())
        secret_key =  current_app.config['globalConfig'].Config.get('General','SecretKey')
        sha = hashlib.sha256()
        sha.update(secret_key.encode('utf-8'))
        sha.update(email.encode('utf-8'))
        sha.update(now.to_bytes(8,byteorder="big"))

        baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
        digest = base64.urlsafe_b64encode(sha.digest()).decode()
        url = baseurl+url_for("membershipupdate.fix2",now=now,digest=digest,email=email)
        debug += f"UTCNOW: {now}\n"
        debug += f"Digest: {digest}\n"
        debug += f"URL: {url}\n"
        debug += f"Debug {isDebug} type: {type(isDebug)}\n"
        emailtext=f"Go to this URL to update your membership: {url}\n\n(Link will expire shortly)\n"

    message = ""
    if isDebug:
        debug += "\n\nDebug mode enabled - Email NOT sent - Email Text:\n\n"+emailtext
    else:
        debug = ""
        try:
            genericEmailSender("info@makeitlabs.com",email,"Fix Membership Link",emailtext)
            message="A message has been sent from info@makeitlabs.com to the email address on-file for this membership, if one has been found. (Make sure it does not go to spam folder)."
        except BaseException as e:
            print (f"Email error: {e}")
            message=f"An error has occured trying to send email - use this link directly, instead: {url}"
    return render_template('message.html',message=message,debug=debug)


# Takes Stripe Subscription Object and subcription id
# Returns subscription and member object
# TODO
def fixMemberSubscription(sub, was_active=False):

    expires = datetime.utcfromtimestamp(sub['current_period_end'])
    created = datetime.utcfromtimestamp(sub['created'])
    updated = datetime.utcnow()
    s = Subscription.query.filter(Subscription.customerid == sub['customer']).first()

    if not s:
        logger.error(f"fixMemberSubscription: No Subscription record found in DB for customer {sub['customer']}")
        return

    db_was_active = str(s.active).strip().lower() in ('true', '1')
    now_active = sub.get('status') in ('active', 'trialing') if isinstance(sub, dict) or hasattr(sub, 'get') else True

    # Add Subscription to Database
    s.paysystem = "stripe"
    s.subid = sub.id
    
    rate_plan = None
    if 'plan' in sub and sub['plan'] and 'id' in sub['plan']:
        rate_plan = sub['plan']['id']
    elif 'items' in sub and 'data' in sub['items'] and len(sub['items']['data']) > 0:
        item = sub['items']['data'][0]
        if 'price' in item and item['price'] and 'id' in item['price']:
            rate_plan = item['price']['id']
        elif 'plan' in item and item['plan'] and 'id' in item['plan']:
            rate_plan = item['plan']['id']

    if rate_plan:
        s.rate_plan = rate_plan
    s.expires_date = expires
    s.created_date = created
    s.updated_date = updated
    s.checked_date = datetime.utcnow()
    if now_active:
        s.active = 'true'
    else:
        s.active = f"false ({sub.get('status')})"
    db.session.commit()

    if now_active and not (was_active and db_was_active):
        db.session.add(Logs(member_id=s.member_id,event_type=eventtypes.RATTBE_LOGEVENT_MEMBER_REACTIVATED.id))
        db.session.add(Logs(member_id=s.member_id,event_type=eventtypes.RATTBE_LOGEVENT_CONFIG_SUB_ACTIVATED_PAYSYS.id,message="Subscription reactivated"))
        db.session.commit()
    authutil.kick_backend()
    return

def sanistring(str):
    if str is None:
        return ""
    return str.strip()

# This is where we get AFTER we have gone through stripe to give it
# an updated credit card
@blueprint.route('/fix_postpay', methods=['GET','POST'])
def fix_postpay():
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    checkout_session_id = request.args.get('session_id')
    if not checkout_session_id:
        return render_template('message.html', title="Error", message="No checkout session ID provided.")

    isDebug = current_app.config['globalConfig'].Config.get('General','Debug').lower() == "true"
    debug = "Postpay\n"

    try:
        checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)
    except BaseException as e:
        return render_template('message.html', title="Error", message=f"Could not retrieve checkout session: {e}")

    debug += f"\n\nid: {checkout_session['id']}\n"
    debug += f"object: {checkout_session['object']}\n"
    debug += f"payment code: {checkout_session['payment_intent']}\n"
    debug += f"object: {checkout_session}\n"

    # Get the SetupIntent and Cust
    # Make it the DEFAULT payment
    si = checkout_session.get('setup_intent')
    c = checkout_session.get('customer')

    if si and c:
        try:
            if isinstance(si, str):
                si_obj = stripe.SetupIntent.retrieve(si)
            else:
                si_obj = si
            debug += f"si: {si_obj}\n"
            pm = si_obj.get('payment_method')
            if pm:
                xx = stripe.Customer.modify(
                    c,
                    invoice_settings={
                        'default_payment_method': pm
                    },
                )
                debug += f"modify: {xx}\n"
        except BaseException as e:
            debug += f"Error in setting default: {e}\n"

    # Also check if customer name/description in Stripe is missing or starts with "MakeIt Labs"
    if c:
        try:
            cust_obj = stripe.Customer.retrieve(c)
            if cust_obj and (not cust_obj.get('name') or not cust_obj.get('description') or (cust_obj.get('description') and cust_obj['description'].startswith("MakeIt Labs"))):
                cust_update = {}
                found_name = None
                ss_temp = stripe.Subscription.list(customer=c)
                for s_item in ss_temp.get('data', []):
                    if s_item.get('metadata', {}).get('names'):
                        found_name = s_item['metadata']['names']
                        break
                if not found_name and cust_obj.get('email'):
                    m = Member.query.filter(or_(func.lower(Member.email) == func.lower(cust_obj['email']), func.lower(Member.alt_email) == func.lower(cust_obj['email']))).first()
                    if m:
                        found_name = f"{m.firstname} {m.lastname}".strip() or m.member.replace('.', ' ')
                if found_name:
                    if not cust_obj.get('name'):
                        cust_update['name'] = found_name
                    if not cust_obj.get('description') or (cust_obj.get('description') and cust_obj['description'].startswith("MakeIt Labs")):
                        cust_update['description'] = found_name
                    if cust_update:
                        stripe.Customer.modify(c, **cust_update)
                        debug += f"Updated customer name/desc in Stripe: {cust_update}\n"
        except BaseException as ce:
            debug += f"Error checking/updating customer name: {ce}\n"

    # Process subscriptions for customer c
    ss = stripe.Subscription.list(customer=c)
    active_subs = [sub for sub in ss.get('data', []) if sub.get('status') in ('active', 'trialing', 'past_due', 'unpaid')]

    message = ""
    if len(active_subs) > 0:
        for s in active_subs:
            was_sub_active = s.get('status') in ('active', 'trialing')
            subid = s['items']['data'][0]['subscription'] if ('items' in s and 'data' in s['items'] and len(s['items']['data']) > 0) else s['id']
            debug += f"Active subscription SubID: {subid} (Status: {s.get('status')})\n"
            
            # Attempt to pay any open invoices
            try:
                open_invoices = stripe.Invoice.list(customer=c, status='open')
                for inv in open_invoices.get('data', []):
                    try:
                        stripe.Invoice.pay(inv['id'])
                        debug += f"Paid open invoice {inv['id']}\n"
                    except BaseException as ie:
                        debug += f"Error paying invoice {inv['id']}: {ie}\n"
            except BaseException as ie:
                debug += f"Error listing open invoices: {ie}\n"

            # Refresh subscription state
            try:
                refreshed_sub = stripe.Subscription.retrieve(s['id'])
            except BaseException:
                refreshed_sub = s

            # Sync with database
            fixMemberSubscription(refreshed_sub, was_active=was_sub_active)

        message = "Your credit card payment method has been successfully updated."
    else:
        debug += f"No active subscription - looking for most recent ended subscription\n"
        ss_ended = stripe.Subscription.list(customer=c, status="ended")
        recent = None
        mostrecent = None
        for s in ss_ended.get('data', []):
            debug += f"Inactive sub: {s.get('id')} cancel_at: {s.get('cancel_at')} ended_at: {s.get('ended_at')} plan: {s.get('plan')}\n"
            ended_val = s.get('ended_at') or s.get('canceled_at')
            if ended_val is not None and (recent is None or ended_val > recent):
                recent = ended_val
                mostrecent = s

        if mostrecent is None:
            message = "Your credit card was updated, but no previous subscription was found to reactivate. Please contact info@makeitlabs.com for help."
        else:
            plan_id = None
            if mostrecent.get('plan') and mostrecent['plan'].get('id'):
                plan_id = mostrecent['plan']['id']
            elif mostrecent.get('items') and mostrecent['items'].get('data') and len(mostrecent['items']['data']) > 0:
                item = mostrecent['items']['data'][0]
                price_obj = item.get('price') or item.get('plan')
                if price_obj and price_obj.get('id'):
                    plan_id = price_obj['id']

            if plan_id:
                try:
                    sub = stripe.Subscription.create(
                        customer=c,
                        metadata=mostrecent.get('metadata', {}),
                        description="Membership renewal",
                        collection_method="charge_automatically",
                        items=[{"price": plan_id}]
                    )
                    debug += f"NewSub: {sub}\n"
                    fixMemberSubscription(sub)
                    message = "Your credit card was updated and your membership has been successfully reactivated!"
                except BaseException as e:
                    debug += f"Error Creating new subscription: {e}\n"
                    message = f"Credit card updated, but error reactivating membership: {e}"
            else:
                message = "Credit card updated, but could not determine previous membership plan to reactivate."

    logger.info(f"Traceback (fix_postpay debug):\n{debug}")
    return render_template('message.html', title="Membership Updated", message=message, debug=debug if isDebug else None)

def register_pages(app):
	app.register_blueprint(blueprint)
