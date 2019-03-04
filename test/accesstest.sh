#!/bin/sh
cd ~/authbackend_bkg
curl  http://testkey:testkey@127.0.0.1:5000/api/v1/resources/frontdoor/acl > ~/new2_doorbot_v1.acl
curl  http://testkey:testkey@127.0.0.1:5000/api/v0/resources/frontdoor/acl > ~/new2_doorbot_v0.acl
#test/doorbot_compare_v1.py > ../doorbot-cmp.txt
#test/denied.py | tee ../denied.txt
diff ../firstmigrate_doorbot_v0.acl ../new2_doorbot_v0.acl
python authserver.py --command querytest > ../indquery_door.txt
