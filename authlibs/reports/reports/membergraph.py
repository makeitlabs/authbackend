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

todaystamp = datetime.now().timestamp()
today = datetime.now().date()
date_array = [0] * 180
mtypes = {}
def mark_dates_in_range(start_timestamp, end_timestamp,count,mtype,active):
    """
    Initializes an array representing the last 180 days and marks days
    covered by the provided date ranges.

    Args:
        entries: A list of dictionaries, where each dictionary has:
                 - 'start_timestamp': The start timestamp (in seconds since epoch).
                 - 'end_timestamp': The end timestamp (in seconds since epoch).

    Returns:
        A list of 180 integers (0 or 1), where the last element represents today,
        the second to last represents yesterday, and so on. A '1' indicates
        that at least one entry covered that day, and '0' indicates no coverage.
    """


    if start_timestamp is None:
        return  # Skip entries with missing timestamps

    if end_timestamp is None:
        end_timestamp = todaystamp

    try:
        start_date = datetime.fromtimestamp(start_timestamp).date()
        end_date = datetime.fromtimestamp(end_timestamp).date()
    except (TypeError, ValueError):
        print(f"Warning: Invalid timestamp format in entry: {end_timestamp} {start_timestamp}")
        sys.exit(-1)
        return

    #print (f"Chek {start_timestamp} {end_timestamp} {start_date} {end_date}\n")
    current_date = start_date
    while current_date <= end_date:
        delta = today - current_date
        days_ago = delta.days

        if 0 <= days_ago < 180:
            index = 179 - days_ago
            #print (f"{days_ago} index {index} for {current_date}")
            date_array[index] =  date_array[index] + count

        if days_ago == 0:
            if mtype not in mtypes:
                mtypes[mtype]=0
            mtypes[mtype] += count
            if not active:
                print ("ERROR NOT ACTIVE!!")
        current_date += timedelta(days=1)


if __name__ == "__main__":
    fix = 0
    leavealone = 0
    err = 0
    stripe.api_version = '2020-08-27'
    stripe.api_key = open("stripenamefix.key").readline().strip()
    subs={}
    since = int((datetime.now() - timedelta(days=180)).timestamp())
    #print (f"SINCE {since}")

    # Status can be "open" or "paid"
    # https://stripe.com/docs/search#search-query-language

    #for x in stripe.Customer.auto_paging_iter(False):
    #for x in stripe.Customer.search(query="-name~\"M\"").auto_paging_iter():
    #    subscriptions = stripe.Subscription.list(customer=x.id)
    #for subscriptions in stripe.Subscription.auto_paging_iter(False):
    #for s in  stripe.Subscription.list(limit=20):
    couponcodes={}
    subcount=0
    processed={}
    for s in stripe.Subscription.search(query=f"canceled_at>{since} or status:\"active\"").auto_paging_iter():
        if s['id'] in processed:
            continue
        if s['plan'] is None:
            continue
        processed[s['id']]= True
        subcount = subcount+1
        #print (s)
        coupon = "No Coupon"
        if 'discount' in s and s['discount'] is not None and 'coupon' in s['discount'] and s['discount']['coupon'] is not None and s['discount']['coupon'] is not None:
            if s['discount']['coupon']['name'] is not None and s['discount']['coupon']['name']  != "":
                coupon = s['discount']['coupon']['name']
            else:
                coupon = s['discount']['coupon']['id']
            couponcodes[s['discount']['coupon']['id']] = coupon
        mcount = 1
        p=s['plan']['id']
        if p in memberships:
            if s['plan']['id'] ==  "produo": mcount=2
            if coupon in exempt: mcount=0
            #print (f"MEMBER: Start={s['start_date']} cancel={s['canceled_at']} {s['ended_at']} plan={s['plan']['id']} Coupon={coupon} mcount={mcount}")
            enddate = None
            if s['canceled_at'] is not None: enddate=s['canceled_at']
            if s['ended_at'] is not None: enddate=s['ended_at']

            if ((s['plan']['active'] == True)
                and (s['canceled_at'] is None)
                and (s['ended_at'] is None)):
                active= True
            else:
                active=False
            t = coupon+" "+s['plan']['id']
            if (mcount != 0):
                mark_dates_in_range(s['start_date'],enddate,mcount,t,active)
            #if t == "99% off in perpetuity pro":
            #    print (f"99pro: {s['metadata']['names']} {s['id']} {subcount}")

    print("HTML:\n</pre>")
    print("<div style='font-family: Arial, sans-serif; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>")
    print("<h2 style='color: #333; margin-top: 0;'>Membership Graph (Past 180 Days)</h2>")
    
    # Generate SVG chart
    max_val = max(date_array) if date_array else 1
    svg_height = 300
    svg_width = 800
    bar_width = svg_width / 180.0
    
    html = f"<svg width='{svg_width}' height='{svg_height}' style='border-bottom: 1px solid #ccc; margin-top: 20px;'>"
    for i, count in enumerate(date_array):
        bar_height = (count / max_val) * (svg_height - 40) if max_val > 0 else 0
        x = i * bar_width
        y = svg_height - 20 - bar_height
        html += f"<rect x='{x}' y='{y}' width='{bar_width - 0.5}' height='{bar_height}' fill='#0d6efd'><title>Day {-179 + i}: {count} members</title></rect>"
    
    # Add labels
    html += f"<text x='0' y='{svg_height - 5}' font-size='12px' fill='#666'>180 Days Ago</text>"
    html += f"<text x='{svg_width}' y='{svg_height - 5}' font-size='12px' fill='#666' text-anchor='end'>Today</text>"
    html += "</svg>"
    
    # Add a summary table
    html += "<table class='table table-striped mt-4'>"
    html += "<tr><th>Timeframe</th><th>Member Count</th></tr>"
    html += f"<tr><td>Today</td><td>{date_array[-1]}</td></tr>"
    html += f"<tr><td>30 Days Ago</td><td>{date_array[-31]}</td></tr>"
    html += f"<tr><td>90 Days Ago</td><td>{date_array[-91]}</td></tr>"
    html += f"<tr><td>180 Days Ago</td><td>{date_array[0]}</td></tr>"
    html += "</table>"
    
    print(html)
    print("</div>\n<pre>")
    sys.exit(0)

