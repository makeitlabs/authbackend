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
    for s in stripe.Subscription.auto_paging_iter():
        #print (s)
        coupon = "No Coupon"
        if 'discount' in s and s['discount'] is not None and 'coupon' in s['discount'] and s['discount']['coupon'] is not None and s['discount']['coupon'] is not None:
            if s['discount']['coupon']['name'] is not None and s['discount']['coupon']['name']  != "":
                coupon = s['discount']['coupon']['name']
            else:
                coupon = s['discount']['coupon']['id']
            couponcodes[s['discount']['coupon']['id']] = coupon
        #print (f"MEMBER: {s['canceled_at']} {s['ended_at']} {s['plan']['active']} {s['plan']['id']}")
        if ((s['plan'] is not None) and ('active' in s['plan']) and (s['plan']['active'] == True)
            and (s['canceled_at'] is None)
            and (s['ended_at'] is None)):
                p =  s['plan']['id']
                if p in memberships:
                    ccc = 1
                    if p == "produo": ccc=2
                    t = f"{p} {coupon}"
                    #if t=="pro 99% off in perpetuity":
                    #    print (f"Pro99L : {s['metadata']['names']}\n")
                    if p not in subs: subs[p]={
                            'count':0, 'coupons':{}}
                    subs[p]['count'] = subs[p]['count']+ccc
                    if coupon not in subs[p]['coupons']: subs[p]['coupons'][coupon]=0
                    subs[p]['coupons'][coupon] = subs[p]['coupons'][coupon]+ccc

    #print (f"Fixed {fix} Left Alone {leavealone} Total {fix+leavealone} Error {err}")
    #print (subs)

    #print (couponcodes)
    #print ("===============")
    print (f"   {' ':50s} {'All':>5s} {'Paid':>5s}")
    all_grand=0
    paid_grand=0
    for s in subs:
        all_total=0
        paid_total=0
        print (f"{s:20s} {' ':50s} {subs[s]['count']}")
        for x in subs[s]['coupons']:
            ccount = subs[s]['coupons'][x]
            cccount = ccount
            if x in exempt: cccount=0
            all_total = all_total + ccount
            paid_total = paid_total + cccount
            all_grand += ccount
            paid_grand += cccount
            print (f"   {x:50s} {ccount:5d} {cccount:5d}")
        print (f"   {' ':50s} {'---':>5s} {'---':>5s}")
        print (f"   {' ':50s} {all_total:5d} {paid_total:5d}")

    print ("")
    print ("Grand Total:")
    print (f"   {' ':50s} {'---':>5s} {'---':>5s}")
    print (f"   {' ':50s} {all_grand:5d} {paid_grand:5d}")

    sys.exit(0)

