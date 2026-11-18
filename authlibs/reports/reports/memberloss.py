#!/usr/bin/python3


import stripe
from datetime import datetime,timedelta
import calendar
import json
import pickle
import re,sys
from pytz import UTC

# Needs rak_customer_write

products = {}

"""
{'100PERCENTOFF': '100PERCENTOFF', 'MILITARYPRO': 'MILITARYPRO', 'w3GA2pSA': 'NonProfit -Free 1yr Memberships', 'PRO4HOBBYIST': 'PRO4HOBBYIST', 'GL0FEquU': '99% off in perpetuity', '9dAkTJ4r': 'Resource Manager Discount', '03q8LXBK': '3 months off', 'LCpqqG55': '100% off in perpetuity- Do NOT use'}
"""
memberships=[
'hobbyist',
'pro',
'produo']

exempt = ['100PERCENTOFF',
'NonProfit -Free 1yr Memberships', 
'100% off in perpetuity- Do NOT use']

if __name__ == "__main__":
    fix = 0
    leavealone = 0
    err = 0
    stripe.api_version = '2020-08-27'
    stripe.api_key = open("stripenamefix.key").readline().strip()
    subs={}

    # Status can be "open" or "paid"
    # https://stripe.com/docs/search#search-query-language

    #for x in stripe.Customer.auto_paging_iter(False):
    #for x in stripe.Customer.search(query="-name~\"M\"").auto_paging_iter():
    #    subscriptions = stripe.Subscription.list(customer=x.id)
    #for subscriptions in stripe.Subscription.auto_paging_iter(False):
    #for s in  stripe.Subscription.list(limit=20):
    couponcodes={}
    since = int((datetime.now() - timedelta(days=30)).timestamp())
    for s in stripe.Subscription.search(query=f"canceled_at>{since}").auto_paging_iter():
        #print (s)
        ss = stripe.Customer.retrieve(s['customer'])
        coupon = "No Coupon"
        if 'discount' in s and s['discount'] is not None and 'coupon' in s['discount'] and s['discount']['coupon'] is not None and s['discount']['coupon'] is not None:
            if s['discount']['coupon']['name'] is not None and s['discount']['coupon']['name']  != "":
                coupon = s['discount']['coupon']['name']
            else:
                coupon = s['discount']['coupon']['id']
            couponcodes[s['discount']['coupon']['id']] = coupon
        ##print (f"MEMBER: {s['metadata']['names']:30s} {s['canceled_at']} {s['ended_at']} {s['plan']['active']} {s['plan']['id']} {s['cancellation_details']}")
        try:
            print (f"{s['metadata']['names']:20s} Since: {datetime.fromtimestamp(ss['created']).date()} Notes: {s['cancellation_details']['comment']}")
        except:
            email = s['email'] if 'email' in s else "<Email Missing>"
            description = s['description'] if 'description' in s else "<Description Missing>"
            created = datetime.fromtimestamp(s['created']).date() if 'created' in s else "<Created Missing>"
            print (f"<Missing Metadata> {description} {email} {created}")
        if ((s['plan']['active'] == True)
            and (s['canceled_at'] is None)
            and (s['ended_at'] is None)):
                p =  s['plan']['id']
                if p in memberships:
                    ccc = 1
                    if p == "produo": ccc=2
                    if p not in subs: subs[p]={
                            'count':0, 'coupons':{}}
                    subs[p]['count'] = subs[p]['count']+ccc
                    if coupon not in subs[p]['coupons']: subs[p]['coupons'][coupon]=0
                    subs[p]['coupons'][coupon] = subs[p]['coupons'][coupon]+ccc


    sys.exit(0)

