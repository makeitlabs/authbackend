#!/usr/bin/python

import json
from datetime import datetime

j = json.load(open("/tmp/stripe_output.json"))

# active True None 1552616181 None None
for x in j:
	#print x['status'], x['plan']['active'], x['ended_at'], x['created'], x['canceled_at'], x['cancel_at']
	if 'plan' in x and x['plan'] and 'active' in x['plan']:
					datetime.utcfromtimestamp(x['current_period_start']).strftime('%Y-%m-%d')
					if x['status'] not in ():
									print "{:10s} {:6} end: {:10s}  cr: {:10s}  cncld: {:10s}  cncl: {:10s}  ps: {:10s}  pe: {:10s} {:20.20s} {:20.20s}".format(
													str(x['status']),
													str(x['plan']['active']),
													"-" if not x['ended_at'] else datetime.utcfromtimestamp(x['ended_at']).strftime('%Y-%m-%d'),
													datetime.utcfromtimestamp(x['created']).strftime('%Y-%m-%d'),
													"-" if not x['canceled_at'] else datetime.utcfromtimestamp(x['canceled_at']).strftime('%Y-%m-%d'),
													"-" if not x['cancel_at'] else datetime.utcfromtimestamp(x['cancel_at']).strftime('%Y-%m-%d'),
													"-" if not x['current_period_start'] else datetime.utcfromtimestamp(x['current_period_start']).strftime('%Y-%m-%d'),
													"-" if not x['current_period_end'] else datetime.utcfromtimestamp(x['current_period_end']).strftime('%Y-%m-%d'),
													x['metadata']['emails'] if 'emails' in x['metadata'] else "--",
													x['metadata']['names'] if 'names' in x['metadata'] else "--"
													)
													#str(x['metadata']))
		
