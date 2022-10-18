#!/bin/sh
cd ~/authbackend_bkg
curl  ${LIVE_URL}/api/v1/resources/frontdoor/acl > ~/live_doorbot_v1.acl
curl  @${LIVE_URL}/api/v0/resources/frontdoor/acl > ~/live_doorbot_v0.acl
#curl  https://bkgtest:${BKGTEST_APIKEY}@${STAGING_URL}/api/v1/resources/frontdoor/acl > ~/staging_doorbot_v1.acl
#curl  https://bkgtest:${BKGTEST_APIKEY}@${STAGING_URL}/api/v0/resources/frontdoor/acl > ~/staging_doorbot_v0.acl
curl  http://bkgtest:${BKGTEST_APIKEY}@127.0.0.1:5000/api/v1/resources/frontdoor/acl > ~/local_doorbot_v1.acl
curl  http://bkgtest:${BKGTEST_APIKEY}@127.0.0.1:5000/api/v0/resources/frontdoor/acl > ~/local_doorbot_v0.acl
echo "V1 DIFFS"
diff ~/live_doorbot_v1.acl ~/local_doorbot_v1.acl
echo "V0 DIFFS"
diff ~/live_doorbot_v0.acl ~/local_doorbot_v0.acl
