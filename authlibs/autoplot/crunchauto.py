#!/usr/bin/python

# vim:expandtab:shiftwidth=2

#import ConfigParser
import icalendar,sys,os,datetime
import stripe
import pytz
import urllib
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
  data['sumary']="{2} Week #{3} - {0} through {1}".format(weekstart.strftime("%b-%d"),weekend.strftime("%b-%d"),weekstart.year,weeknum)

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
            summary['errors']+="No Attendees"
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

  return (errors,warnings,debug,data,billables)

def do_payment():
  Config=ConfigParser.ConfigParser()
  Config.read("makeit.ini")
  stripe.api_key = Config.get('Stripe','token')
  #stripe.api_key = "sk_test_4eC39HqLyjWDarjtT1zdp7dc" # TEST KEY
  #print stripe.SKU.list(limit=99)
  #print stripe.Customer.list(limit=99)

  print """
  ** INVOICE ITEM
  """
  print stripe.InvoiceItem.create(
    #customer="cus_J0mrDmtpzbfYOk", # Stripe Test Customer
    customer="cus_BrcR4XAzDYl87s", # MIL Brad Goodman
    #price="sku_IpxYEyVzmdmEy6", # TEST
    price="price_1IOZ6DI573ycCeJ1voBFqlDP", # MIL ZERO DOLLAR PLOT
  )
  print """
  ** INVOICE
  """
  inv = stripe.Invoice.create(
    customer="cus_J0mrDmtpzbfYOk",
    description="Auto Plot Rental Weekly Automaitc Invoice"
  )
  print inv
  print """
  ** INVOICE PAY
  """
  print "PAYING",inv['id']
  pay = stripe.Invoice.pay(inv)
  print pay


def auto_cli(*args,**kwargs):
    (errors,warnings,debug,data,billables) = crunch_calendar()
    print "***\n***\n WARNINGS:"
    for w in warnings:
      print "  "+w
    print "***\n***\n ERRORS:"
    for e in errors:
      print "  "+e
    print "***\n***\n DEBUG:"
    for d in debug:
      print "  "+d
    print """***
    BILLING
    ***
    """
    print billables
