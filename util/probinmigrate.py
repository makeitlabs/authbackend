#!/usr/bin/python


from authlibs.init import authbackend_init, createDefaultUsers
import authlibs.utilities as authutil
from  authlibs import eventtypes
from authlibs.db_models import db, ApiKey, Role, UserRoles, Member, Resource, MemberTag, AccessByMember, \
			Blacklist, Waiver, Subscription, Node, NodeConfig, Tool, KVopt, ProLocation, ProBin

def log_bin_event(bin,event,commit=0):
	f=[]
	if bin.location_id:
		l = ProLocation.query.filter(ProLocation.id == bin.location_id).one_or_none()
		if l:
			f.append("Loc:%s" % l.location)
	if bin.name:
		f.append("Bin:%s" % bin.name)
	f.append("%s" % ProBin.BinStatuses[bin.status])
	message = " ".join(f)
	authutil.log(event,member_id=bin.member_id,message=message,commit=commit)

garage="""
6,,Patrick Lefebvre,Bob Higgins,Corey Hudson,Dale Savoy,Chris WeinBeck,Dave Shevett,Bryan cote
5,gokhan sozmen,Peter Dibble,Arthur Ercolini,Wayne Geiser,Arnie Howard,Christina Pitsch,Mordecai Veldt,Paul Duffy
4,David MacDonald,Marc Hebert,,Rob Taylor,Ian Cook,Dave Ritchie and Helene Andersson,bill shongar,Steve Richardson
3,Machine Shop,Glenn Della-Monica,Matt marulla,Dennis Holt,Steven Wolsky,drew Pattersen,Tom goll,Seth Allen
2,burpeau,,Chris Fox,Shawn tafe,John white,Doug Clougher,Sean Hensley,Kevin dunivan
1,Ron Lavoie,Brent,Evan dudzik,Anthony Bernabei,David Yandell,Michael Watson,Peter Vatne,Shawn taffe
"""

def addrec(loc,m):
				lrec = ProLocation.query.filter(ProLocation.location == loc).one_or_none()
				if not lrec:
					raise BaseException( "LOCATION {0} NOT FOUND".format(loc))
				brec = ProBin()
				brec.member_id = m.id
				brec.location_id = lrec.id
				brec.status = 2
				db.session.add(brec)
				log_bin_event(brec,eventtypes.RATTBE_LOGEVENT_PROSTORE_ASSIGNED.id)
				print brec

app=authbackend_init(__name__)
with app.app_context():
				cols = ['A','B','C','D','E','F','G','H']
				row = 6
				for x in garage.split("\n"):
					x=x.strip()
					sp = x.split(",")[1:]
					if len(sp)>0:
						colno=0
						for n in sp:
							names = n.split()
							if len(names) >= 2:
											m = Member.query.filter(Member.lastname.ilike(names[1])).filter(Member.firstname.ilike(names[0])).all()
											for mm in m:
												loc= "Garage-%s-%s" % (cols[colno],row)
												print loc,cols[colno],row,mm,names
												addrec(loc,mm)
							colno +=1
						row -= 1
				db.session.commit()
		

"""
pawelko,Russ havrylik
Mike swatko
Joe Peitz
"""

cleanspace="""
,Joe Rothweiler,
,Laura Allen,Nathan Allen
,Ryan hoult,Bill Lawson
,Simon tong,Susan Tong
"""

with app.app_context():
				cols = ['A','B']
				row = 4
				for x in cleanspace.split("\n"):
					x=x.strip()
					sp = x.split(",")[1:]
					if len(sp)>0:
						colno=0
						for n in sp:
							names = n.split()
							if len(names) >= 2:
											m = Member.query.filter(Member.lastname.ilike(names[1])).filter(Member.firstname.ilike(names[0])).all()
											for mm in m:
												loc= "Cleanspace-%s-%s" % (cols[colno],row)
												print loc,cols[colno],row,mm,names
												addrec(loc,mm)
							colno +=1
						row -= 1
				db.session.commit()
