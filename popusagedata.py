#!/usr/bin/python
# vim:tabstop=2:shiftwidth=2:expandtab


from authlibs.templateCommon import *
from authlibs.init import authbackend_init
import argparse
import datetime
import random

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
		parser.add_argument("--days","-d",help="days",default=7,type=int)
		parser.add_argument("--minidle","-i",help="Min idle minutes",default=2,type=int)
		parser.add_argument("--maxidle","-I",help="Max idle minutes",default=20,type=int)
		parser.add_argument("--minactive","-a",help="Min active minutes",default=5,type=int)
		parser.add_argument("--maxactive","-A",help="Max active minutes",default=60,type=int)
		parser.add_argument("--minbetween","-b",help="Min active minutes",default=5,type=int)
		parser.add_argument("--maxbetween","-B",help="Max active minutes",default=4*60,type=int)
		(args,extras) = parser.parse_known_args(sys.argv[1:])

    print args
    app=authbackend_init(__name__)

    with app.app_context():
			now=datetime.datetime.now()
			dt=datetime.datetime.now()-datetime.timedelta(days=args.days)


			uids=[]
			for u in ('testuser','testarm','testrm','testtrainer'):
							uids.append(Member.query.filter(Member.member==u).one().id)

			(tid,rid) = db.session.query(Tool.id,Tool.resource_id).filter(Tool.name=="TestTool").one()

			#print "UIDs",uids,"TID",tid,"RID",rid
			while (dt < datetime.datetime.now()):
				idle = random.randint(args.minidle,args.maxidle)
				active = random.randint(args.minactive,args.maxactive)
				enabled = idle+active
				dt += datetime.timedelta(minutes=enabled)

				db.session.add(UsageLog(time_logged = dt,
								time_reported = dt,
								tool_id = tid,
								resource_id = rid,
								member_id = uids[random.randint(0,len(uids)-1)],
								idleSecs = idle,
								activeSecs = active,
								enabledSecs = enabled))

				unused  = random.randint(args.minbetween,args.maxbetween)
				dt += datetime.timedelta(minutes=unused)
			db.session.commit()

			
			
