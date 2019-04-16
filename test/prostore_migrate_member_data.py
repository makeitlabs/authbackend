#!/usr/bin/python


from authlibs.init import authbackend_init, createDefaultUsers
from authlibs.db_models import db, ApiKey, Role, UserRoles, Member, Resource, MemberTag, AccessByMember, \
			Blacklist, Waiver, Subscription, Node, NodeConfig, Tool, KVopt

garage="""
6,,Patrick Lefebvre,Bob Higgins,Corey Hudson,Dale Savoy,Chris WeinBeck,Dave Shevett,Bryan cote
5,gokhan sozmen,Peter Dibble,Arthur Ercolini,Wayne Geiser,Arnie Howard,Christina Pitsch,Mordecai Veldt,Paul Duffy
4,David MacDonald,Marc Hebert,,Rob Taylor,Ian Cook,Dave Ritchie and Helene Andersson,bill shongar,Steve Richardson
3,Machine Shop,Glenn Della-Monica,Matt marulla,Dennis Holt,Steven Wolsky,drew Pattersen,Tom goll,Seth Allen
2,burpeau,,Chris Fox,Shawn tafe,John white,Doug Clougher,Sean Hensley,Kevin dunivan
1,Ron Lavoie,Brent,Evan dudzik,Anthony Bernabei,David Yandell,Michael Watson,Peter Vatne,Shawn taffe
"""

app=authbackend_init(__name__)
with app.app_context():
				cols = ['A','B','C','D','E','F','G','H']
				row = 6
				for x in garage.split("\n"):
					x=x.strip()
					sp = x.split(",")[1:]
					if len(sp)>0:
						print sp
						colno=0
						for n in sp:
							names = n.split()
							print names
							if len(names) >= 2:
											m = Member.query.filter(Member.lastname.ilike(names[1])).filter(Member.firstname.ilike(names[0])).all()
											for mm in m:
												print cols[colno],row,mm
							colno +=1
						row -= 1
		

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
						print sp
						colno=0
						for n in sp:
							names = n.split()
							print names
							if len(names) >= 2:
											m = Member.query.filter(Member.lastname.ilike(names[1])).filter(Member.firstname.ilike(names[0])).all()
											for mm in m:
												print cols[colno],row,mm
							colno +=1
						row -= 1
