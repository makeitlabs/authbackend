#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs import accesslib
import stripe
from datetime import datetime,timedelta
import calendar
import json
import pickle
import re
from pytz import UTC

blueprint = Blueprint("finrep", __name__, template_folder='templates', static_folder="static",url_prefix="/finrep")

def do_report(month,year):
    products = {}
    stripe.api_version = '2020-08-27'
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','Token')
    # Status can be "open" or "paid"
    # https://stripe.com/docs/search#search-query-language

    startperiod = datetime(year, month, 1)
    startperiod = startperiod.replace(tzinfo=UTC)
    # Calculate the end of the month
    lastday = calendar.monthrange(year, month)[1]
    endperiod = datetime(year, month, lastday, 23, 59, 59)  # Set the time to the end of the day
    endperiod = endperiod.replace(tzinfo=UTC)



    print("Start period:", startperiod, " to End period:", endperiod)
    print("Start period:", startperiod.timestamp(), " to End period:", endperiod.timestamp())

    group={}
    for x in [x.strip() for x in open("repgroups.dat","r").readlines()]:
        sp = x.split()
        group[sp[0]] = sp[1]
    print (group)

    allProducts =   stripe.Product.auto_paging_iter(False)
    for p in  allProducts:
        print (p['id'],p['name'])
        if p['id'] not in products:
              products[p['id']] = {}
              products[p['id']]['name']=p['name']
              products[p['id']]['count'] = 0
              products[p['id']]['total'] = 0
              products[p['id']]['items'] = []


    invoices = stripe.Invoice.auto_paging_iter(
        created={"gte": int((startperiod-timedelta(days=16)).timestamp()), "lte": int((endperiod+timedelta(days=16)).timestamp())}
    )

    for invoice in invoices:

        print("Invoice ID:", invoice.id, " Created:", datetime.fromtimestamp(invoice.created))
        print ("   INVOICE:",invoice['amount_paid'], invoice['status'],invoice['billing_reason'])
        print ("   FINALIZED:",invoice.status_transitions.paid_at)

        # See if invoice was FINALIZED within given period!!

        if ((invoice.status_transitions.paid_at is not None) and (invoice.status_transitions.paid_at >= startperiod.timestamp()) and (invoice.status_transitions.paid_at <= endperiod.timestamp())):
         for l in invoice['lines']['data']:


            # Process it
            product = None
            if l['plan'] is not None and 'product' in l['plan'] and l['plan']['product'] is not None: product = l['plan']['product']
            if 'price' in l and 'product' in l['price'] and l['price']['product'] is not None: product = l['price']['product']

            desc = l['description']
            if desc is None: desc = l['invoice_item']

            desc = re.sub(r'[^\x00-\x7F]+', '', desc).strip()


            origproduct = product
            if product in group:
                #print ("SUB",product,group[product])
                product = group[product]

            #print ("-- LINEITEM:",l['amount'], desc,product)
            #print (l)

            #print ("INVOICE DISC",invoice.discount)
            #print ("II DISCs",l.discounts)
            #print ("II DISC Amrss",l.discount_amounts)

            amount = l['amount']
            for d in l.discount_amounts:
                print ("DISCOUNT",d)
                amount -= d['amount']

            applied_balance = invoice.ending_balance - invoice.starting_balance
            if ((applied_balance >= 0) and (invoice.starting_balance < 0)):
                # Paid from an APPLIED BALANCE (i.e. not)
                amount -= applied_balance

            if product is not None:
                if product not in products:
                      #print ("ADD",product)
                      products[product]={}
                      products[product]['name']=product
                      products[product]['count'] = 0
                      products[product]['total'] = 0
                      products[product]['items'] = []

                products[product]['count'] += 1
                products[product]['total'] += amount
                products[product]['items'].append({
                    'amount': amount,
                    'description': desc,
                    'customer': invoice['customer_email'],
                    'product': origproduct,
                    'invoice': invoice.id,
                    'status': invoice['status']
                    })
        else:
            print ("***** NOT WITHIN FINALIZED PERIOD ****")

    # pickle.dump(gen,open("invoices.data","wb"))
    print ()
    print ()
    print ("=========== TOTAL =============")
    print ()
    print ()
    total = 0
    report = []
    for p in products:
        #print (products[p])
        if products[p]['count'] > 0:
            #print (f"{p:20}: {products[p]['name']:50} {products[p]['count']:6} ${products[p]['total']/100.0:>8.2f}")
            r={
                "product": p,
                "count": products[p]['count'],
                "name": products[p]['name'],
                "total": f"${products[p]['total']/100.0:>8.2f}",
                "items":[]
                }
            total += products[p]['total']
            for i in products[p]['items']:
                #print (f"    -- {i['product']:15}  ${i['amount']/100:>8.2f}    {i['invoice']} {i['customer']} {i['description']} {i['status']}")
                r['items'].append({
                    "product":i['product'],
                    "amount":f"${i['amount']/100.0:>8.2f}",
                    "invoice":i['invoice'],
                    "customer":i['customer'],
                    "description":i['description'],
                    })
            report.append(r)
    #print (f"{'TOTAL:':>79} ${total/100.0:>8.2f}")
    return (report,f"${total/100.0:>8.2f}")




@blueprint.route('/', methods=['GET','POST'])
@roles_required(['Admin','Finance'])
@login_required
def finrep():
    """(Controller) Display Tools and controls"""
    now = datetime.now()
    if 'year' in request.form and 'month' in request.form:
        month = int(request.form['month'])
        year = int(request.form['year'])
        message = ""
        if (((year*12)+month) >= ((now.year*12)+now.month)): message="Warning: Data is incomplete"
        report,total = do_report(int(request.form['month']),int(request.form['year']))
        return render_template('finrep.html',report=report,total=total,month=month,year=year,message=message)
    month = now.month
    year = now.year
    return render_template('finrep.html',month=month,year=year,message="Select a month and year to report")

def register_pages(app):
	app.register_blueprint(blueprint)
