# vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from datetime import datetime
from .. import accesslib
from .. import ago
import subprocess
import glob

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("vending", __name__, template_folder='templates', static_folder="static",url_prefix="/vending")

# --------------------------------------
# Routes
#  /test : Show (HTTP GET - members()), Create new (HTTP POST - member_add())
#  /test/<id> - Some ID
# --------------------------------------

# ------------------------------------------------------------
# Logs  
#
# Things log like crazy. Therefore logs are designed to
# be cheap to write, and to be compartimentalizable so
# that they don't interfere with other stuff.
#
# So we put logs in a separate databse. Maybe someday this
# could be a completely different type of datastore.
#
# Because of this, we can't do relational queries between
# the log and main databases. 
#
# Because of all this, logs are expensive to read. This might
# not be too bad because we don't read them all that often.
# ------------------------------------------------------------

@blueprint.route('/', methods=['GET'])
@login_required
def vending():
  if current_user.privs('Useredit','Finance'):
    return redirect(url_for('vending.summary'))
  else:
    return redirect(url_for('vending.vendingUser',id=current_user.member))

@blueprint.route('/user/<string:id>', methods=['GET'])
@login_required
def vendingUser(id):
    if (not current_user.privs('Finance')) and id != current_user.member:
       flash("You cannot view that user",'warning')
       return redirect(url_for('index'))

    m = Member.query.filter(Member.member == id).one_or_none()
    if (m is None):
       flash("Member does not exist",'warning')
       return redirect(url_for('index'))
    mid = m.id

    eastern = dateutil.tz.gettz('US/Eastern')
    utc = dateutil.tz.gettz('UTC')
    now = datetime.now()
    dbq = db.session.query(VendingLogs).filter(VendingLogs.member_id == mid).order_by(VendingLogs.time_logged.desc())
    db_logs = dbq.all()
    doneby_ids = set(l.doneby for l in db_logs if l.doneby)
    members = {}
    if doneby_ids:
        for m2 in Member.query.filter(Member.id.in_(doneby_ids)).all():
            members[m2.id] = {'first': m2.firstname, 'last': m2.lastname, 'member': m2.member}
    logs = []
    for l in db_logs:
        r={}
        r['datetime']=l.time_logged.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)

        (r['when'],r['ago'],r['othertime'])=ago.ago(r['datetime'],now)


        if not l.doneby:
            r['doneby'] = ""
            r['admin_id']=""
        elif l.doneby in members:
            if not members[l.doneby]['last']:
              r['doneby'] = members[l.doneby]['member']
            else:
              r['doneby'] = str(members[l.doneby]['last'])+", "+str(members[l.doneby]['first'])
            r['admin_id']=members[l.doneby]['member']
        else:
            r['doneby']="Member #"+str(l.doneby)

        r['invoice'] = l.invoice if l.invoice is not None else ""
        r['product'] = l.product if l.product is not None else ""
        r['comment'] = l.comment if l.product is not None else ""
        r['doneby'] = l.doneby if l.doneby is not None else ""
        r['oldBalance'] = "${0:0.2f}".format(float(l.oldBalance)/100.0)
        r['newBalance'] = "= ${0:0.2f}".format(float(l.newBalance)/100.0)
        r['totalCharge'] = "" if l.totalCharge is None else "${0:0.2f}".format(float(l.totalCharge)/100.0)
        r['purchaseAmount'] = "" if l.purchaseAmount is None else "- ${0:0.2f}".format(float(l.purchaseAmount)/100.0)
        r['amountAdded'] = "" if l.addAmount is None else "+ ${0:0.2f}".format(float(l.addAmount)/100.0)
        r['surcharge'] = "" if l.surcharge is None else "${0:0.2f}".format(float(l.surcharge)/100.0)
        logs.append(r)

    meta={}
    if current_user.privs('Useredit','Finance','RATT'):
        meta['nomembersearch']=True
    else:
        meta['nomembersearch']=False


    username = m.firstname + " "+ m.lastname
    if m.balance is None:
      balance = "$0.00"
    else:
      balance = "${0:0.2f}".format(float(m.balance)/100.0)
    return render_template('vending.html',logs=logs,meta=meta,currentBalance=balance,username=username,member_id=m.member)


@blueprint.route('/summary', methods=['GET'])
@login_required
@roles_required(['Admin','Finance'])
def summary():
    mall = Member.query.filter(Member.balance != 0).all()
    balances=[]
    total=0
    for m in mall:
        if m.balance is None:
          balance = "$0.00"
        else:
          balance = "${0:0.2f}".format(float(m.balance)/100.0)
          total += m.balance
        balances.append({
            "balance":balance,
            "id":m.id,
            "member":m.member,
            "name":m.firstname+" "+m.lastname
            })
    total = "${0:0.2f}".format(float(total)/100.0)
    return render_template('summary.html',balances=balances,total=total)

@blueprint.route('/user/<string:id>/manual_credit', methods=['POST'])
@login_required
@roles_required(['Admin','Finance'])
def manual_credit(id):
    if not current_user.privs('Finance'):
       flash("You cannot do that",'warning')
       return redirect(url_for('vending.vendingUser',id=id))

    m = Member.query.filter(Member.member == id).one_or_none()
    if (m is None):
       flash("Member does not exist",'warning')
       return redirect(url_for('index'))

    amount_str = request.form.get('amount', '0')
    try:
        amount_cents = int(float(amount_str) * 100)
    except ValueError:
        flash("Invalid amount",'warning')
        return redirect(url_for('vending.vendingUser',id=id))

    comment = request.form.get('comment', 'Manual Credit')

    if m.balance is None:
        old_balance = 0
        m.balance = amount_cents
    else:
        old_balance = m.balance
        m.balance += amount_cents

    vl = VendingLogs(
        member_id=m.id,
        doneby=current_user.id,
        oldBalance=old_balance,
        addAmount=amount_cents,
        totalCharge=0,
        newBalance=m.balance,
        comment=comment
    )
    db.session.add(vl)
    db.session.commit()

    flash("Added ${0:0.2f} manual credit to {1}'s account.".format(amount_cents/100.0, m.member), "success")
    return redirect(url_for('vending.vendingUser',id=id))

def register_pages(app):
	app.register_blueprint(blueprint)
