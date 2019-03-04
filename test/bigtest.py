#!/usr/bin/python

import sys,re,os,urllib2,urllib,requests
skip_pages="""/api/v1/payments/update
/google_login/google/authorized
/api/v1/reloadacl
/api/cron/nightly
"""

api="""
/api/v1/members
/api/v1/resources
/api/v1/whoami
/api/v3/test
/api/v1/test
"""

basic="""
/member
/authorize
/logs
/authorize/membersearch/*
#/slack
"""

noprivs_mustfail="""
/member/252/edit
/member/252/access
/member/252/tags
/tools/5000
/reports/blacklist
/member/tags/lookup
/resources/frontdoor
/member/admin
/payments
/reports
/waivers
/apikeys
/apikeys/1
/tools
/nodes
/kvopts
/resources
/api/ubersearch/brad
/member/Brad.Goodman
"""

mustfail="""
/member/Does.Not.Exist
/resource/DoesNotexist
/tool/asdfsdfgDoesNotexist
/node/DoesNotExist
/tool/9999
/member/9999/tags
/resource/9999
/member/9999/edit
/member/9990/access
"""

internal_err="""
"""

api_tests = [
	{'url':"/api/v1/node/node1/config"},
	{'url':"/api/v1/members","access":"any"},
	{'url':"/api/v1/whoami"},
	{'url':"/api/v1/test","access":"any"},
	{'url':"/api/v3/test","access":"any"},
	{'url':"/api/membersearch/admin"},
	{'url':"/api/v1/resources/frontdoor/acl"},
	{'url':"/api/v0/resources/frontdoor/acl"},
	{'url':"/api/v1/memberprivs/252"}
]
later="""
/payments/fees/charge
/member/tags/lookup
/google_login/google
/payments/missing
/payments/reports
/payments/manual
/payments/update
/payments/test
/payments/fees
/reports/blacklist
/waivers/update
/member/updatebackends
/member/admin
/member/test
/user/resend-email-confirmation
/user/edit_user_profile
/user/change-password
/user/change-username
/user/forgot-password
/user/manage-emails
/logs/large.csv
/user/sign-out
/user/register
/test/useredit
/user/sign-in
/user/invite
/test/anyone
/test/oauth
/test/admin
/test/std
/authorize/
/resources/
/resources/
/payments/
/comments/
/comments/
/waivers/
/reports/
/apikeys/
/apikeys/
/whoami
/logout
/search
/member/
/member/
/kvopts/
/kvopts/
/login
/index
/nodes/
/nodes/
/tools/
/tools/
/belog/
/slack
/logs/
/
/api/v1/resources/<string:id>/acl
/api/v0/resources/<string:id>/acl
/api/v1/node/<string:node>/config
/api/v1/mac/<string:mac>/config
/payments/missing/assign/<string:assign>
/payments/manual/extend/<member>
/payments/manual/expire/<member>
/payments/manual/delete/<member>
/member/tags/delete/<string:tag_ident>
/api/v1/members/<string:id>
/authorize/membersearch/<string:search>
/authorize/static/<path:filename>
/resources/static/<path:filename>
/resources/<string:resource>/delete
/resources/<string:resource>/list
/resources/<string:resource>/log
/payments/membership/<string:membership>
/payments/static/<path:filename>
/comments/static/<path:filename>
/waivers/static/<path:filename>
/reports/static/<path:filename>
/apikeys/static/<path:filename>
/apikeys/<string:apikey>/delete
/apikeys/<string:apikey>/list
/member/static/<path:filename>
/kvopts/static/<path:filename>
/member/<string:id>/access
/member/<string:id>/access
/kvopts/<string:kvopt>/delete
/member/<string:id>/edit
/member/<string:id>/tags
/member/<string:id>/tags
/nodes/static/<path:filename>
/tools/static/<path:filename>
/belog/static/<path:filename>
/nodes/<string:node>/delete
/tools/<string:tool>/delete
/nodes/<string:node>/list
/tools/<string:tool>/list
/nodes/<string:node>/log
/tools/<string:tool>/log
/user/reset-password/<token>
/user/confirm-email/<token>
/logs/static/<path:filename>
/user/email/<id>/<action>
/api/ubersearch/<string:ss>
/api/static/<path:filename>
/resources/<string:resource>
/resources/<string:resource>
/payments/<string:id>
/apikeys/<string:apikey>
/apikeys/<string:apikey>
/member/<string:id>
/kvopts/<string:kvopt>
/kvopts/<string:kvopt>
/static/<path:filename>
/nodes/<string:node>
/nodes/<string:node>
/tools/<string:tool>
/tools/<string:tool>"""

def finderror(url,r):
	if r.status_code == 500:
		raise BaseException ("%s internal error" %(url))
	if r.status_code != 200:
		return "%s"%r.status_code
	for x in r.text.split("\n"):
		if x.find("-bkg-flash=\"danger\"") >=0 : return "danger"
		if x.find("-bkg-flash=\"warning\"") >=0 : 
			return "warning"

	return 

BASE="http://127.0.0.1:5000"

query_args = { 'username':'admin', 'password':'admin' }
req = requests.Session()
r = req.post(BASE+"/login/check",data=query_args)
print "LOGIN",r.status_code
if r.status_code != 200:
	raise BaseException("Admin login failed")

for x in (basic+noprivs_mustfail).split("\n"):
	if x=="": continue
	if x[0]=="#": continue
	url = BASE+x
	r = req.get(url)
	print url,r.status_code
	if r.status_code != 200:
		raise BaseException ("%s code %s (Needed 200)" %(url,r.status_code))
	err = finderror(url,r)
	if err:
		raise BaseException ("%s FLASHED %s " %(url,err))

for x in mustfail.split("\n"):
	if x=="": continue
	if x[0]=="#": continue
	url = BASE+x
	r = req.get(url)
	err = finderror(url,r)
	print url,r.status_code,err
	if not err:
		raise BaseException ("%s did not flash error" %(url))

for x in internal_err.split("\n"):
	if x=="": continue
	if x[0]=="#": continue
	url = BASE+x
	r = req.get(url)
	if r.status_code != 500:
		raise BaseException ("%s did not return 500" %(url))
	print url,r.status_code

# Check without privs

query_args = { 'username':'noprivs', 'password':'noprivs' }
req = requests.Session()
r = req.post(BASE+"/login/check",data=query_args)
print "LOGIN",r.status_code
for x in noprivs_mustfail.split("\n"):
	if x=="": continue
	if x[0]=="#": continue
	url = BASE+x
	r = req.get(url)
	if r.status_code == 500:
		raise BaseException ("%s internal error" %url)
	if not err:
		raise BaseException ("%s did not flash error" %(url))
	print url,r.status_code,err

# Do API tests - WITHOUT login
req = requests.Session()
for x in api_tests:
	url = BASE+x['url']
	r = req.get(url)
	if 'access' not in x or x['access'] != "any":
					if r.status_code < 400 :
						raise BaseException ("%s API Should have failed auth, but got %d" % (url,r.status_code))
	print url,r.status_code

# Do API tests - WITH login
req = requests.Session()
for x in api_tests:
	url = BASE+x['url']
	r = req.get(url, auth=('testkey', 'testkey'))
	if r.status_code != 200:
		raise BaseException ("%s API failed %d" % (url,r.status_code))
	print url,r.status_code

# Let's get granular w/ V0 ACL checking...

url = BASE+"/api/v0/resources/frontdoor/acl"
r = req.get(url, auth=('testkey', 'testkey'))
if r.status_code != 200:
	raise BaseException ("%s API failed %d" % (url,r.status_code))
allowed=0
denied=0
other=0
for x in  r.text.split("\n"):
	sp = x.split(",")
	if sp[3] == "allowed": allowed+=1
	elif sp[3] == "denied": denied +=1
	else: other +=1

print "V0 frontdoor allowed",allowed,"denied",denied,"other",other
if ((allowed > 370) or (allowed < 270) or (other > 0)):
	raise BaseException("V0 ACL doesn't seem to have returned good values")


# Let's get granular w/ V1 ACL checking...

url = BASE+"/api/v1/resources/frontdoor/acl"
r = req.get(url, auth=('testkey', 'testkey'))
if r.status_code != 200:
	raise BaseException ("%s API failed %d" % (url,r.status_code))
rec= r.json()
allowed=0
denied=0
other=0
for x in rec:
	if x['allowed'] == "allowed": allowed+=1
	elif x['allowed'] == "false": denied+=1
	elif x['allowed'] == "denied": denied+=1
	else: 
		print "Got odd V1 frontdoor ACL value for %s: %s" %(x['member'],x['allowed'])
		other +=1
	
print "V1 frontdoor allowed",allowed,"denied",denied,"other",other
if ((allowed > 370) or (allowed < 270) or (other > 0)):
	raise BaseException("V1 ACL doesn't seem to have returned good values")
