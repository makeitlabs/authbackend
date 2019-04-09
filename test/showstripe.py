#!/usr/bin/python
# vim:tabstop=2:shiftwidth=2

import json,sys
from datetime import datetime
import argparse
import stripe
import ConfigParser

def getSubscriptions(status=None):
		Config = ConfigParser.ConfigParser({})
		Config.read('makeit.ini')
		stripe.api_key = Config.get('Stripe','token')
    '''Get all Subscriptions'''
    if status is None:
        status = "all"
    subscriptions = []
		print "Fetching subscription data"
    subs = stripe.Subscription.list(status=status,limit=50)
    for s in subs.auto_paging_iter():
        subscriptions.append(s)
        #print(s)
		print "Done."
		json.dump(subscriptions,open("/tmp/stripe_output.json","w"),indent=2)
    return subscriptions


parser=argparse.ArgumentParser()
parser.add_argument("-d","--download",help="Download Stripe data",action="store_true")
parser.add_argument("-l","--long",help="Log format",action="store_true")
parser.add_argument("--plan",help="Show Plan Data",action="store_true")
parser.add_argument("--csv",help="Show Plan Data",action="store_true")
parser.add_argument("--period",help="Show Current Period",action="store_true")
parser.add_argument("--id",help="Show Identifiers",action="store_true")
parser.add_argument("--metadata",help="Show Sub Metadata",action="store_true")
parser.add_argument("--custom",help="Custom format")
args= parser.parse_args()


if args.download:
	getSubscriptions()

j = json.load(open("/tmp/stripe_output.json"))
# active True None 1552616181 None None
first=True
for x in j:
	#print x['status'], x['plan']['active'], x['ended_at'], x['created'], x['canceled_at'], x['cancel_at']
	if 'plan' in x and x['plan'] and 'active' in x['plan']:
		datetime.utcfromtimestamp(x['current_period_start']).strftime('%Y-%m-%d')
		if x['status'] not in (): # Weird unused filter
			pa = {
				'customer':str(x['customer']),
				'id':str(x['id']),
				'status':str(x['status']),
				'plan_name':str(x['plan']['name']),
				'plan_id':str(x['plan']['id']),
				'active':str(x['plan']['active']),
				'ended_at':"-" if not x['ended_at'] else datetime.utcfromtimestamp(x['ended_at']).strftime('%Y-%m-%d'),
				'ended_at_full':"-" if not x['ended_at'] else datetime.utcfromtimestamp(x['ended_at']).strftime('%Y-%m-%d %H:%M %P'),
				'created':datetime.utcfromtimestamp(x['created']).strftime('%Y-%m-%d'),
				'created_full':datetime.utcfromtimestamp(x['created']).strftime('%Y-%m-%d %H:%M %P'),
				'created_raw':x['created'],
				'canceled_at':"-" if not x['canceled_at'] else datetime.utcfromtimestamp(x['canceled_at']).strftime('%Y-%m-%d'),
				'canceled_at_full':"-" if not x['canceled_at'] else datetime.utcfromtimestamp(x['canceled_at']).strftime('%Y-%m-%d %H:%M %P'),
				'cancel_at':"-" if not x['cancel_at'] else datetime.utcfromtimestamp(x['cancel_at']).strftime('%Y-%m-%d'),
				'cancel_at_full':"-" if not x['cancel_at'] else datetime.utcfromtimestamp(x['cancel_at']).strftime('%Y-%m-%d %H:%M %P'),
				'canceled_at_raw':x['canceled_at'],
				'cancel_at_raw':x['cancel_at'],
				'created_raw':x['created'],
				'cape':"Y" if x['cancel_at_period_end'] else "N",
				'period_start':"-" if not x['current_period_start'] else datetime.utcfromtimestamp(x['current_period_start']).strftime('%Y-%m-%d'),
				'period_start_full':"-" if not x['current_period_start'] else datetime.utcfromtimestamp(x['current_period_start']).strftime('%Y-%m-%d %H:%M %P'),
				'period_end':"-" if not x['current_period_end'] else datetime.utcfromtimestamp(x['current_period_end']).strftime('%Y-%m-%d'),
				'period_end_full':"-" if not x['current_period_end'] else datetime.utcfromtimestamp(x['current_period_end']).strftime('%Y-%m-%d %H:%M %P'),
				'period_start_raw':x['current_period_start'],
				'period_end_raw':x['current_period_end'],
				'email':x['metadata']['emails'].strip() if 'emails' in x['metadata'] else "--",
				'name':x['metadata']['names'].strip() if 'names' in x['metadata'] else "--",
				'metadata':x['metadata'] 
			}
			if args.long:
							print """
Status:           {status}
Active:           {active}
Ended At:         {ended_at_full}
Created:          {created_full}
Canceled:         {cancel_at_full}
Cancel:           {cancel_at_full}
Cncl at Perd End: {cape}
Period Start:     {period_start_full}
Period End:       {period_end_full}
Email:            {email}
Name:             {name}
plan name:        {plan_name}
plan id:          {plan_id}

""".format(**pa)


			elif args.csv:
				out=[]
				if first:
					for v in sorted(pa):
						out += [v]
					print ",".join(["\""+xx+"\"" for xx in out])
					out=[]
					first=False
				for v in sorted(pa):
					out += [str(pa[v]) if (v in pa and pa[v]) else ""]
				print ",".join(["\""+v.replace('"','\\"')+"\"" for v in out])
			else:
				if args.custom:
					fmtstr = args.custom
				else:
					fmtstr= "{status:10s} {active:6} end: {ended_at:10s}  cr: {created:10s}  cncld: {canceled_at:10s}  cncl: {cancel_at:10s} cape:{cape:1s}"
					fmtstr+=" {email:20.20s} "
					fmtstr+=" {name:20.20s}"
					#fmtstr += " raw: {created_raw}"
					if args.plan: fmtstr += " {plan_id:5.5s}"
					if args.plan: fmtstr += " {plan_name:10.10s}"
					if args.period: fmtstr += " ps: {period_start:10s}  pe: {period_end:10s}"
					if args.id: fmtstr += " cust: {customer:20.20s}  id: {id:20.20s}"
					if args.metadata: fmtstr += " meta: {metadata:20.20s}"
				print fmtstr.format(**pa)

