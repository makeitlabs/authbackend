#!/usr/bin/python2
import sqlite3, re, time
import random
from authlibs import dbutil

male=open("test/male_names.txt")
female=open("test/female_names.txt")
surnames=open("test/surnames.txt")

con = dbutil.connect_db()
cur=con.cursor()

cur.execute("delete from members;")
for x in range(0,250):
	if (x%4 == 0):
		m = female.readline().strip().title()
	else:
		m = male.readline().strip().title()

	s = surnames.readline().strip().title()
	uid = m.lower()+"."+s.lower()
	email = uid+"@makkeitlabs.com"

	phone = "603-"+"{:03d}".format(random.randint(101,999))+"-"+"{:04d}".format(random.randint(1,9999))

	full=m+" "+s
	print m,s,full,uid,email
	sqlstr = """insert into members (firstname,lastname,name,member,phone,alt_email,updated_date,access_enabled,active)
							VALUES ('%s','%s','%s','%s','%s','%s',DATETIME('now'),'1','1');
					 """ % (m,s,full,uid,phone,email)
	cur.execute(sqlstr)
con.commit()

cur.execute("delete from resources;")
sqlstr = """
insert into resources(name,description) values
	("laser","Rabbit Laser"),
	("FullSpectrum","Full Spectrum Laser"),
	("AutoLift","Automotive Lift");
"""
cur.execute(sqlstr)
con.commit()

