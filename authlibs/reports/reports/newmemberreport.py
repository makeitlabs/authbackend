#!/usr/bin/python3


import stripe
from datetime import datetime,timedelta
import calendar
import json
import pickle
import re,sys
from pytz import UTC
import time
import sqlite3
import time

# Needs rak_customer_write

products = {}
# select membership,customerid,member_id from subscriptions;
def time_ago(seconds):
    intervals = (
        ('year', 31536000),  # 60 * 60 * 24 * 365
        ('month', 2592000),  # 60 * 60 * 24 * 30
        ('week', 604800),    # 60 * 60 * 24 * 7
        ('day', 86400),      # 60 * 60 * 24
        ('hour', 3600),      # 60 * 60
        ('minute', 60),
        ('second', 1),
    )

    orig = seconds
    result = []

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                result.append(f"{value:3.0f} {name}")
            else:
                result.append(f"{value:3.0f} {name}s")
            break

    return ', '.join(result) + " ago"

def query(cust):
    conn = sqlite3.connect('../../../makeit.db')  # Replace 'my_database.db' with your desired database name
    cursor = conn.cursor()

    # Create a table (if it doesn't exist)
    q = f'select member_id from subscriptions where customerid = "{cust}";';
    #print (q)
    v = cursor.execute(q)

    #print (f"GET {cust}")


    try:
        memberid = v.fetchall()[0][0]
        ## GET LOG COUNT
        conn = sqlite3.connect('log.db')  # Replace 'my_database.db' with your desired database name
        cursor = conn.cursor()

        # Create a table (if it doesn't exist)
        q = f'select count(*) from log where member_id = "{memberid}" and resource_id=1;';
        #print (q)
        v = cursor.execute(q)
        return (v.fetchall()[0][0])

    except:
        return (0)



if __name__ == "__main__":
    fix = 0
    leavealone = 0
    err = 0
    stripe.api_version = '2020-08-27'
    stripe.api_key = open("stripenamefix.key").readline().strip()

    # Status can be "open" or "paid"
    # https://stripe.com/docs/search#search-query-language

    since = datetime.now() - timedelta(days=90)
    #for x in stripe.Customer.auto_paging_iter(False):
    #for x in stripe.Customer.search(query="-name~\"M\"").auto_paging_iter():
    #print (f"QUERY created>{since.timestamp()}")
    for x in stripe.Customer.search(query=f"created>{int(since.timestamp())}").auto_paging_iter():
        if  x.description is None:
                    # print (f"No Description {x.name}")
                    err += 1
        else:
            dt = datetime.fromtimestamp(x.created)
            #print (dt,since)
            subscriptions = stripe.Subscription.list(customer=x.id)
            for s in subscriptions:
                c = query (x.id)
                if 'emails' in s.metadata and 'names' in s.metadata:
                    print (f"{x.description:30s} {time_ago(time.time()-x.created):>15s} {c}")

    sys.exit(0)

