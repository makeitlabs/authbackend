#!/usr/bin/python3

"""
# authenticate and save the cookie contents in local file cookie.txt with switch '-c'
curl -k -X POST --data '{"username": "brad_api", "password": "bradapizzzbrad"}' --header 'Content-Type: application/json' -c cookie.txt https://10.25.0.1:443/api/auth/login
# responds with json data

# pass the local file cookie.txt with switch '-b'
#curl -k -X GET -b cookie.txt https://10.25.0.1/proxy/network/api/s/default/self
#curl -k -X GET -b cookie.txt https://10.25.0.1/proxy/network/api/s/default/stat/device
#curl -k -X GET -b cookie.txt https://10.25.0.1/proxy/network/api/s/default/stat/device-basic
curl -k -X GET -b cookie.txt https://10.25.0.1/proxy/network/api/s/default/stat/device
# responds with proper json
"""

import requests
import json
from requests.auth import HTTPDigestAuth
import urllib3
import time
import os
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
                result.append(f"{value} {name}")
            else:
                result.append(f"{value} {name}s")
            break

    return ', '.join(result) + " ago"
# Endpoint URL
login_url = 'https://10.25.0.1:443/api/auth/login'

# MUST be ordered in priority - i.e. live clients firs
url_list =  [
    'https://10.25.0.1/proxy/network/api/s/default/stat/sta',
    'https://10.25.0.1/proxy/network/api/s/default/rest/user']

# List of things to skip
reported = {}

# Credentials
form_data = {
    'username': os.environ['UNIFI_API_USERNAME'],
    'password': os.environ['UNIFI_API_PASSWORD']
}

headers = {
    'Content-Type': 'application/json'
}

# First request with Digest Authentication
response = requests.post(login_url, data=json.dumps(form_data),headers=headers,verify=False)

#print (dir(response))
#print (response.raw)
#print (response.reason)
#print (response.text)
#print (json.dumps(response.json(),indent=2))
#login_time = response.json()['login_time']
login_time = time.time()
# Check if the request was successful
if response.status_code == 200:
    # Extract the cookie from the response
    cookies = response.cookies

    # Use the cookie to make another request to the same endpoint
    for url in url_list:
        response_with_cookie = requests.get(url, cookies=cookies,verify=False)

        # Check if the second request was successful
        if response_with_cookie.status_code == 200:
            # Process the JSON data
            json_data = response_with_cookie.json()
            #print(json_data)
            #print (json.dumps(response_with_cookie.text,indent=2))
            for x in json_data['data']:
                n = ""
                if 'name' in x and x['name'] is not None: n = x['name']
                if 'hostname' in x and x['hostname'] is not None and x['hostname'] != "": n = x['hostname']
                if x == "" and 'oui' in x and x['oui'] is not None: n = x['oui']
                ip = ""
                mac = ""
                if 'ip' in x: ip = x['ip']
                if ip == "" and 'last_ip' in x and x['last_ip'] != "": ip = x['last_ip']
                if 'mac' in x and x['mac'] is not None: 
                    mac = x['mac']
                    if mac in reported:
                        #print (f"SKIPPING {mac}")
                        continue
                reported[mac]=True
                devname = ""
                if 'device_name' in x and x['device_name'] is not None: devname = x['device_name']
                if 'oui' in x and x['oui'] is not None and devname == "": devname = x['oui']
                tm = x['last_seen']
                if 'disconnect_timestamp' in x and x['disconnect_timestamp'] > x['last_seen']:
                    tm = x['disconnect_timestamp']
                #tm = x['last_seen']-login_time
                tm = tm-login_time
                #print (x)
                print (f"{n:30.30} {mac:20.20} {devname:30.30} {time_ago(-tm):15.15}   {ip} ")
            #print (json.dumps(json_data,indent=2))
        else:
            print(f'Second request failed with status code: {response_with_cookie.status_code}')
else:
    print(f'First request failed with status code: {response.status_code}')
