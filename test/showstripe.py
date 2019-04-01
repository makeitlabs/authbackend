#!/usr/bin/python
# vim:tabstop=2:shiftwidth=2

import json,sys
from datetime import datetime
import argparse

j = json.load(open("/tmp/stripe_output.json"))

parser=argparse.ArgumentParser()
parser.add_argument("-l","--long",help="Log format",action="store_true")
(args,extras) = parser.parse_known_args(sys.argv[1:])
# active True None 1552616181 None None
for x in j:
	#print x['status'], x['plan']['active'], x['ended_at'], x['created'], x['canceled_at'], x['cancel_at']
	if 'plan' in x and x['plan'] and 'active' in x['plan']:
		datetime.utcfromtimestamp(x['current_period_start']).strftime('%Y-%m-%d')
		if x['status'] not in ():
			pa = {
				'status':str(x['status']),
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
				'email':x['metadata']['emails'] if 'emails' in x['metadata'] else "--",
				'name':x['metadata']['names'] if 'names' in x['metadata'] else "--"
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

""".format(**pa)


			else:
							print "{status:10s} {active:6} end: {ended_at:10s}  cr: {created:10s}  cncld: {canceled_at:10s}  cncl: {cancel_at:10s} cape:{cape:1s}  ps: {period_start:10s}  pe: {period_end:10s} {email:20.20s} {name:20.20s}".format(**pa)

