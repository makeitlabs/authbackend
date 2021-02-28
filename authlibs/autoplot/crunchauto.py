#!/usr/bin/python


#import ConfigParser
import icalendar,sys,os,datetime
import stripe
import pytz
import urllib
import json
from dateutil import tz

from ..templateCommon import  *

def utctolocal(dt):
  from_zone = tz.gettz('UTC')
  to_zone = tz.gettz('America/New_York')
  utc = dt.replace(tzinfo=from_zone)
  l = utc.astimezone(to_zone)
  return l

weekday=['Sun','Mon','Tues','Wed','Thurs','Fri','Sat'] # OUR Sunday=0 Convention!!
def crunch_calendar(rundate=None):
  #ICAL_URL = Config.get('autoplot','ICAL_URI')
  ICAL_URL = current_app.config['globalConfig'].Config.get("autoplot","ICAL_URI")
  g = urllib.urlopen(ICAL_URL)
  cal = icalendar.Calendar.from_ical(g.read())
  g.close()
  if rundate:
    now = datetime.datetime.strptime(rundate,"%Y-%m-%d").replace(tzinfo=tz.gettz('America/New York'))
  else:
    now = datetime.datetime.now().replace(tzinfo=tz.gettz('America/New York'))
  ## ADJUST HERE FOR TZ! (i.e. If we run Midnight on Sunday don't want LAST week's run
  dow = now.weekday() # 0=Monday
  dow = (dow+1) %8  #0=Sunday
  weeknum = int(now.strftime("%U")) 
  #print "weeknum",weeknum,"Weekday",weekday[dow]
  weekstart = (now - datetime.timedelta(days=dow))
  weekstart = weekstart.replace(hour=0,minute=0,second=0,microsecond=0)
  weekend = weekstart + datetime.timedelta(days=7)
  #print "WEEKSTART",weekstart,"through",weekend
  errors=[]
  warnings=[]
  billables=[]
  summaries=[]
  debug=[]
  data={}

  debug.append("{2} Week #{3} - {0} through {1}".format(weekstart.strftime("%b-%d"),weekend.strftime("%b-%d"),weekstart.year,weeknum))
  data['title']="Auto Plot Lease {2} Week #{3} - {0} through {1}".format(weekstart.strftime("%b-%d"),weekend.strftime("%b-%d"),weekstart.year,weeknum)
  data['lease-id']="autoplot-lease-{2}-Week{3:02}".format(weekstart.strftime("%b-%d"),weekend.strftime("%b-%d"),weekstart.year,weeknum)
  data['weekid']="{2:04}-{3:02}".format(weekstart.strftime("%b-%d"),weekend.strftime("%b-%d"),weekstart.year,weeknum)

  for component in cal.walk():
      #print component.name
      #print dict(component)
      #print dir(component)
      #print(component.get('summary'))
      #print(component.get('dtstart'))
      #print(component.get('dtend'))
      #print(component.get('dtstamp'))
      summary={'errors':[],'warnings':[]}
      if component.name == 'VEVENT':
        print component
        billable=False
        members=[]
        event={}
        calstart = utctolocal(component['DTSTART'].dt)
        calend =  utctolocal(component['DTEND'].dt)
        #print "SUMMARY",component['SUMMARY']
        #print "START",calstart
        #print "END",calend
        short = calstart.strftime("%b-%d %H:%M ")+component['SUMMARY']
        if 'ORGANIZER' in component: 
          # print "ORGANIZER",component['ORGANIZER']
          for p in component['ORGANIZER'].params:
            pass #print "_  ---- ",p,component['ORGANIZER'].params[p]
        #print "NOW",now
        if (weekstart <= calstart) and (calend <= weekend):
          if 'ATTENDEE' not in component: 
            summary['errors'].append("No Attendees")
          else:
            if isinstance(component['ATTENDEE'],list):
              attlist = component['ATTENDEE']
            else:
              attlist = [component['ATTENDEE']]
            for a in attlist:
              #print "  -- Attendee:",a
              #print "  -- Params:"
              for p in a.params:
                pass #print "_  ---- ",p,a.params[p]
              if 'CUTYPE' in a.params and a.params['CUTYPE'] == 'INDIVIDUAL':
                members.append(a.params['CN'])
              """
              print "  -- DIR",dir(a)
              print 
              print "  -- ICAL",type(a.to_ical),dir(a.to_ical())
              print 
              """
          hrs=(calend-calstart).total_seconds()/3600
          print "*** CURRENT!!! {0} Hours total".format(hrs)
          if (hrs <= 24): 
            summary['warnings'].append("Partial day entry - NOT BILLING")
          elif (hrs <= 167):
            summary['warnings'].append("Entry isn't quite full week, but billing anyway")
          if (hrs > 24):
            if len(members) > 1:
              summary['errors'].append("More than one member assigned")
            elif len(members) == 0:
              summary['errors'].append("No attendees in calendar entry")
            else:
              if not members[0].lower().endswith("@makeitlabs.com"):
                summary['errors'].append("Non-MIL email")
              else:
                billable=True
                print "*** BILLABLE"
                event['summary']=short
                event['member']=members[0]
            #if component['SUMMARY'].strip().lower().startswith("rental"):
            #  print "** IS RENTAL"

          # Figure out what to do based on Summary
          if (len(summary['errors']) == 0) and billable:
            billables.append(event)
          for e in summary['errors']:
            errors.append(short + ": "+e)
          for w in summary['warnings']:
            warnings.append(short + ": "+w)
        
      """
      for x in component:
        print x,type(component[x]),
        if (isinstance(component[x],icalendar.prop.vDDDTypes)):
           print component.decoded(x)
           print type(component[x].dt)
           print component[x].dt
        else:
           print component.decoded(x)
        #print dir(component[x])
      print
      """


  if len(billables) ==0:
    warnings.append("WARNING - NO BILLABLES THIS WEEK!")
  elif len(billables) >1:
    errors.append("ERROR - MULTIPLE BILLABLES THIS WEEK!")

  if (len(errors) != 0):
    data['Decision']='error'
  elif (len(billables) == 0):
    data['Decision']='no_bill'
  else:
    data['Decision']='bill'
  return (errors,warnings,debug,data,billables)

def do_payment(customer,price,leaseid,description,test=False,pay=False):
  errors=[]
  warnings=[]
  debug=[]
  stripe.api_key = current_app.config['globalConfig'].Config.get('autoplot','stripe_token')
  #stripe.api_key = "sk_test_4eC39HqLyjWDarjtT1zdp7dc" # TEST KEY
  #print stripe.SKU.list(limit=99)
  #print stripe.Customer.list(limit=99)

  debug.append("Process Payment customer {0} Price {1} leaseid {2}".format(customer,price,leaseid))
  print "Process Payment customer {0} Price {1} leaseid {2}".format(customer,price,leaseid)
  debug.append("Description: {0}".format(description))
  print "Description: {0}".format(description)

  """
  """
  print """
  ** GET EXISTING INVOICE ITEM
  """

  # Get existing outstanding items in Stripe to invoice
  lastItem=None
  pendingleases={}
  while True:
      ii= stripe.InvoiceItem.list(
        limit=2,
        #customer="cus_J0mrDmtpzbfYOk", # Stripe Test Customer
        customer=customer, # MIL Brad Goodman
        starting_after=lastItem
        )

      print "EXISTING ITEMS"
      print ii
      if ii:
          for d in ii['data']:
              lastItem=d['id']
              if 'metadata' in d:
                  print "Metadata ",d['metadata']
                  if 'X-MIL-lease-id' in d['metadata']:
                    pendingleases[d['metadata']['X-MIL-lease-id']] = { 'invoice':d['invoice'],'invoiceitem':d['id']}
                    warnings.append("Lease already pending: "+d['metadata']['X-MIL-lease-id']+" in invoice "+str(d['invoice']))
                  else:
                    warnings.append("No metadata in item")
      if not ii['has_more']: break
 
  print "PENDING LEASES",pendingleases
  
  # If our new entry is not here - create item in stripe
  if leaseid not in pendingleases:
      print """
      ** ADD INVOICE ITEM
      """
      
      ii= stripe.InvoiceItem.create(
        #customer="cus_J0mrDmtpzbfYOk", # Stripe Test Customer
        customer=customer, # MIL Brad Goodman
        description=description,
        #price="sku_IpxYEyVzmdmEy6", # TEST
        price=price, # MIL ZERO DOLLAR PLOT
        metadata={
                'X-MIL-lease-id':leaseid,
                'X-MIL-lease-location':'autoplot'
            }
        )
      pendingleases[leaseid]= { 'invoice':None,'invoiceitem':ii['id']}
      None # We have a pending now, with no invoice
      debug.append("Created Invoice Item {0} for lease {1}".format(ii['id'],leaseid))

  # If we have not created an invoice with this item in it - do so
  if leaseid not in pendingleases or pendingleases[leaseid]['invoice'] is None:
      print """
      ** INVOICE
      """
      inv = stripe.Invoice.create(
        customer=customer,
        description=description,
        auto_advance=False,
        collection_method="charge_automatically",
        metadata={
                'X-MIL-lease-id':leaseid,
                'X-MIL-lease-location':'autoplot'
            }
        #period_start=,
        #period_end=json
      )
      pendingleases[leaseid]['invoice']=inv['id']
      debug.append("Created Invoice {0} for lease {1}".format(inv['id'],leaseid))
      status="invoiced"
  else:
    status="already_invoiced"
    warnings.append("Using existing Invoice {0} for lease {1}".format(pendingleases[leaseid]['invoice'],leaseid))
    # We have a current lease - let's look at it!
    print "INSPECT INVOICE"
    print "***"
    inv = stripe.Invoice.retrieve(pendingleases[leaseid]['invoice'])

  print json.dumps(inv,indent=2)

  # If unpaied - pay it!
 
  if inv['paid'] == True and inv['status']=='paid':
    debug.append("Already paid")
    print "** Aleady Paid!"
    status="already_paid_stripe"
  elif pay:
    print "** Paying!"
    debug.append("Paying")
    try:
      stripe.Invoice.pay(inv['id'])
      debug.append("Payment Done")
      print "** Paid!"
      status="paid"
    except BaseException as e:
      errors.append("Payment failed on invoice {0}: {1}".format(inv['id'],e))
      print "** Payment failed!"
      status="payment_failed"

  
  #print "DELETEING INVOICE"
  #print stripe.Invoice.delete(inv['id'])
  #debug.append("Created Invoice {0} for lease {1}".format(inv['id'],leaseid))

  return (errors,warnings,debug,status)


