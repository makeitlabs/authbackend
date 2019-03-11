#!/bin/sh
cd ~/authbackend_bkg
python authserver.py --command updatepayments | tee ~/stripedebug.txt
python authserver.py --command memberpaysync 2>&1 | tee ~/memberpaysync_debug.txt
curl  http://testkey:testkey@127.0.0.1:5000/api/v1/resources/frontdoor/acl > ~/new_doorbot_v1.acl
curl  http://testkey:testkey@127.0.0.1:5000/api/v0/resources/frontdoor/acl > ~/new_doorbot_v0.acl
test/doorbot_compare_v1.py > ../doorbot-cmp.txt
test/denied.py | tee ../denied.txt

diff ../firstmigrate_doorbot_v0.acl ../new_doorbot_v0.acl
