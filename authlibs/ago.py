#!/usr/bin/python

import time,datetime
def whichday(then):
	when = ""
	now = datetime.datetime.now().date()
	thenday = then.date()
	if (now.year == thenday.year) and (now.month == thenday.month) and (now.day == thenday.day):
		when = "Today "

	yesterday = now - datetime.timedelta(days=1)
	if (yesterday.year == thenday.year) and (yesterday.month == thenday.month) and (yesterday.day == thenday.day):
		when = "Yesterday "

	if ((now-thenday).days < 270) and (when != "Today ") and (when != "Yesterday "): 
		when = thenday.strftime("%A ")

	if ((now-thenday).days <6 ):	
		pass
	elif (yesterday.year == thenday.year):	
		when += thenday.strftime("%b %d")
	else:
		when += thenday.strftime("%b %d, %Y")

	when += " "
	when += then.strftime("%I:%M %p")
	return when
	
def ago(tm,since=datetime.datetime.now()):
	daysago = since-tm
	return delta(daysago,tm)

def TimeDeltaString(tm):
	return delta(tm,None)

def roundunit(num):
	if num < 10:
		return "{0:.1f}".format(num)
	else:
		return "{0}".format(int(round(num)))
	

def delta(daysago,tm,short=False):
	ctxstr=""
	if (daysago.days == 0) and (daysago.seconds < 60  ):
		if short:
			agostr = "{0} Sec".format(roundunit(daysago.seconds))
		else:
			agostr = "{0} Seconds".format(roundunit(daysago.seconds))
		if tm: ctxstr = tm.strftime("%I:%M:%S")
	elif (daysago.days == 0) and (daysago.seconds < 3600  ):
		agostr = "{0} Min".format(roundunit(daysago.seconds / 60.0))
		if tm: ctxstr = tm.strftime("%I:%M:%S")
	elif (daysago.days == 0):
		agostr = "{0} Hours".format(roundunit(daysago.seconds / 3600.0))
		if tm: ctxstr = tm.strftime("%I:%M %p")
	elif (daysago.days < 7):
		agostr = "{0} Days".format(roundunit(daysago.days))
		if tm: ctxstr = tm.strftime("%a %I:%M %p")
	elif (daysago.days < 21):
		agostr = "{0} Days".format(roundunit(daysago.days))
		if tm: ctxstr = tm.strftime("%a %b-%d %I:%M %p")
	elif (daysago.days < 90):
		agostr = "{0} Weeks".format(roundunit(daysago.days /7))
		if tm: ctxstr = tm.strftime("%a %b-%d %I:%M %p")
	elif (daysago.days < 365):
		agostr = "{0} Months".format(roundunit(daysago.days / 30))
		if tm: ctxstr = tm.strftime("%a %b %d %I:%M %p")
	else:
		agostr = "{0:.1f} Years".format(roundunit(daysago.days/365.0))
		if tm: ctxstr = tm.strftime("%a, %b %d, %Y")
	if tm:
		return whichday(tm),agostr,ctxstr
	else:
		return agostr



if __name__ == "__main__":
		print ago(datetime.datetime.now())
		print ago(datetime.datetime.now()-datetime.timedelta(seconds=5))
		print ago(datetime.datetime.now()-datetime.timedelta(minutes=5))
		print ago(datetime.datetime.now()-datetime.timedelta(hours=5))
		print ago(datetime.datetime.now()-datetime.timedelta(hours=25))
		print ago(datetime.datetime.now()-datetime.timedelta(days=3))
		print ago(datetime.datetime.now()-datetime.timedelta(days=5))
		print ago(datetime.datetime.now()-datetime.timedelta(days=18))
		print ago(datetime.datetime.now()-datetime.timedelta(weeks=5))
		print ago(datetime.datetime.now()-datetime.timedelta(weeks=35))
		print ago(datetime.datetime.now()-datetime.timedelta(weeks=50))
		print ago(datetime.datetime.now()-datetime.timedelta(weeks=250))
		print TimeDeltaString(datetime.timedelta(seconds=6))
		print TimeDeltaString(datetime.timedelta(minutes=6))
		print TimeDeltaString(datetime.timedelta(weeks=6))
