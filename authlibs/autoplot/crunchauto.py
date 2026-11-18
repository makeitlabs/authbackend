#!/usr/bin/python


#import ConfigParser
import icalendar,sys,os,datetime
import stripe
import pytz
import urllib
import json
from dateutil import tz

from ..templateCommon import  *

def utctolocal(dt,endofdate=False):
  from_zone = tz.gettz('UTC')
  to_zone = tz.gettz('America/New_York')

  if isinstance(dt,datetime.datetime): 
    #dt = dt.replace(tzinfo=from_zone)
    dt = dt.astimezone(to_zone)
  else:
    if endofdate:
      dt = datetime.datetime.combine(dt,datetime.time(hour=23,minute=59,second=59,tzinfo=to_zone))
    else:
      dt = datetime.datetime.combine(dt,datetime.time(tzinfo=to_zone))
  return dt

weekday=['Sun','Mon','Tues','Wed','Thurs','Fri','Sat'] # OUR Sunday=0 Convention!!
def crunch_calendar(rundate=None):
  #ICAL_URL = Config.get('autoplot','ICAL_URI')
  ICAL_URL = current_app.config['globalConfig'].Config.get("autoplot","ICAL_URI")
  g = urllib.request.urlopen(ICAL_URL)
  data=  g.read()
  print(data)
  cal = icalendar.Calendar.from_ical(data)
  g.close()

  """
  g = urllib.urlopen(ICAL_URL)
  print g.read()
  g.close()
  """

  if rundate:
    now = datetime.datetime.strptime(rundate,"%Y-%m-%d").replace(tzinfo=tz.gettz('America/New York'))
  else:
    now = datetime.datetime.now().replace(tzinfo=tz.gettz('America/New York'))
  #print "CRUNCH EFFECTIVE RUNDATE",rundate
  ## ADJUST HERE FOR TZ! (i.e. If we run Midnight on Sunday don't want LAST week's run
  dow = now.weekday() # 0=Monday
  dow = (dow+1) %7  #0=Sunday
  weeknum = int(now.strftime("%U")) 
  #print "weeknum",weeknum,"Weekday",weekday[dow],"DOW",dow
  weekstart = (now - datetime.timedelta(days=dow))
  weekstart = weekstart.replace(hour=0,minute=0,second=0,microsecond=0)
  weekend = weekstart + datetime.timedelta(days=7)
  weekend = weekend - datetime.timedelta(seconds=1)
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
      if component.name != 'VEVENT':
        print ("NOT A VEVENT!!!",component.name)
      else:
        #print "VEVENT",component
        billable=False
        members=[]
        event={}
        calstart = component['DTSTART'].dt
        #print "CALSTART",calstart
        calstart = utctolocal(calstart)
        calend =  component['DTEND'].dt
        calend =  utctolocal(calend,endofdate=True)
     
        #print "SUMMARY",component['SUMMARY']
        #print "START",calstart
        #print "END",calend
        if 'ORGANIZER' in component: 
          # print "ORGANIZER",component['ORGANIZER']
          for p in component['ORGANIZER'].params:
            pass #print "_  ---- ",p,component['ORGANIZER'].params[p]
        #print "CHECK",weekstart,"<",calstart,
        #print "aand",calend,"<",weekend
        #if (weekstart <= calstart) and (calend <= weekend):

        rrule =  None
        weeks=1
        if 'RRULE' in component and 'COUNT' in component['RRULE'] and 'FREQ' in component['RRULE']: 
           rrule=component['RRULE']
           #print "RRULE",calstart.strftime("%b-%d %H:%M ")+component['SUMMARY'],
           #print rrule['COUNT'][0],rrule['FREQ'][0]
           if rrule['FREQ'][0]== "WEEKLY":
             weeks = rrule['COUNT'][0]

        for weekno in range(0,weeks):
          short = calstart.strftime("%b-%d %H:%M ")+component['SUMMARY']
          if (calstart <= weekend) and (weekstart < calend):
            #print "THISWEEK calendar",calstart,calend
            #print "THISWEEK curweel",weekstart,weekend
            #print "PROCESS",short
            #print "WEEK IN SERIES",weekno
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
            #print "*** CURRENT!!! {0} Hours total".format(hrs)
            if (hrs <= 24): 
              summary['warnings'].append("Partial day entry - NOT BILLING")
            elif (hrs <= 167):
              summary['warnings'].append("Entry isn't quite full week, but billing anyway")
            if (hrs > 24):
              if len(members) > 1:
                summary['errors'].append("More than one member assigned: "+str(", ".join(members)))
              elif len(members) == 0:
                summary['errors'].append("No attendees in calendar entry")
              else:
                if not members[0].lower().endswith("@makeitlabs.com"):
                  summary['errors'].append("Non-MIL email: "+str(members[0]))
                else:
                  billable=True
                  #print "*** BILLABLE"
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
          #print "END PARSE"
          calstart = calstart + datetime.timedelta(weeks=1)
          calend = calend + datetime.timedelta(weeks=1)
        # End of FOR for weeks
        
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
  #print "Process Payment customer {0} Price {1} leaseid {2}".format(customer,price,leaseid)
  debug.append("Description: {0}".format(description))
  #print "Description: {0}".format(description)

  """
  """
  print ("""
  ** GET EXISTING INVOICE ITEM
  """)

  # Get existing outstanding items in Stripe to invoice
  lastItem=None
  pendingleases={}
  while True:
      ii= stripe.InvoiceItem.list(
        limit=99,
        #customer="cus_J0mrDmtpzbfYOk", # Stripe Test Customer
        customer=customer, # MIL Brad Goodman
        starting_after=lastItem
        )

      #print "EXISTING ITEMS"
      #print ii
      if ii:
          for d in ii['data']:
              lastItem=d['id']
              if 'metadata' in d:
                  #print "Metadata ",d['metadata']
                  if 'X-MIL-lease-id' in d['metadata']:
                    pendingleases[d['metadata']['X-MIL-lease-id']] = { 'invoice':d['invoice'],'invoiceitem':d['id']}
                    warnings.append("Lease already pending: "+d['metadata']['X-MIL-lease-id']+" in invoice "+str(d['invoice']))
                  else:
                    warnings.append("No metadata in item")
      if not ii['has_more']: break
 
  #print "PENDING LEASES",pendingleases
  
  # If our new entry is not here - create item in stripe
  if leaseid not in pendingleases:
      print ("""
      ** ADD INVOICE ITEM
      """)
      
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
          print ("""
          ** INVOICE
          """)
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
    print ("INSPECT INVOICE")
    print ("***")
    inv = stripe.Invoice.retrieve(pendingleases[leaseid]['invoice'])

  print (json.dumps(inv,indent=2))

  # If unpaied - pay it!
 
  if inv['paid'] == True and inv['status']=='paid':
    debug.append("Already paid")
    #print "** Aleady Paid!"
    status="already_paid_stripe"
  elif pay:
    #print "** Paying!"
    debug.append("Paying")
    try:
      #stripe.Invoice.pay(inv['id'])
      stripe.Invoice.pay(inv)
      debug.append("Payment Done")
      #print "** Paid!"
      status="paid"
    except BaseException as e:
      errors.append("Payment failed on invoice {0}: {1}".format(inv['id'],e))
      print ("** Payment failed!")
      status="payment_failed"

  
  #print "DELETEING INVOICE"
  #print stripe.Invoice.delete(inv['id'])
  #debug.append("Created Invoice {0} for lease {1}".format(inv['id'],leaseid))

  return (errors,warnings,debug,status)


