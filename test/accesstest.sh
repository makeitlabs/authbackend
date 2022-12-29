#!/bin/sh
wget -O ~/live_doorbot_v1.acl  ${LIVE_URL}/api/v1/resources/frontdoor/acl
wget -O ~/live_doorbot_v0.acl ${LIVE_URL}/api/v0/resources/frontdoor/acl
wget --no-check-certificate -O ~/local_doorbot_v1.acl  ${STAGING_URL}/api/v1/resources/frontdoor/acl
wget --no-check-certificate -O ~/local_doorbot_v0.acl ${STAGING_URL}/api/v0/resources/frontdoor/acl
#echo "V1 DIFFS"
#diff ~/live_doorbot_v1.acl ~/local_doorbot_v1.acl
echo "V0 DIFFS"
diff ~/live_doorbot_v0.acl ~/local_doorbot_v0.acl

echo "V1 Diff Tool"
test/doorbot_compare_v1.py ~/live_doorbot_v1.acl ~/local_doorbot_v1.acl
