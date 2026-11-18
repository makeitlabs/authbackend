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

if __name__ == "__main__":
    fix = 0
    leavealone = 0
    err = 0
    stripe.api_version = '2020-08-27'
    stripe.api_key = open("stripenamefix.key").readline().strip()

    # Status can be "open" or "paid"
    # https://stripe.com/docs/search#search-query-language

    for x in stripe.Customer.auto_paging_iter(False):
    #for x in stripe.Customer.search(query="-name~\"M\"").auto_paging_iter():
        if x.description is None or x.name is None or x.description.startswith("MakeIt Labs"):
            #subscriptions = stripe.Subscription.list(customer=x.id,status="canceled")
            subscriptions = stripe.Subscription.list(customer=x.id)
            for s in subscriptions:
                if 'names' in s.metadata:
                        fix += 1
                        print (f"FIX: desc='{x.description}' name='{x.name}' -> '{s.metadata['names']}'")
                        x.description = s.metadata['names']
                        x.name = s.metadata['names']
                        x.save()
                else:
                    print (f"No Name in Metadata! {x.id} {s.id} {x.name} {x.description}")
                    err += 1
        else:
            #print (f"LeaveAlone: {x.description} {x.name}")
            leavealone +=1

    print (f"Fixed {fix} Left Alone {leavealone} Total {fix+leavealone} Error {err}")
    sys.exit(0)

