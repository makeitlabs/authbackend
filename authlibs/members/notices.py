# vim:shiftwidth=2

from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago
from authlibs.accesslib import addQuickAccessQuery
from ..google_admin import genericEmailSender



def log_bin_event(bin,event,commit=0):
	f=[]
	if bin.location_id:
		l = ProLocation.query.filter(ProLocation.id == bin.location_id).one_or_none()
		if l:
			f.append("Loc:%s" % l.location)
	if bin.name:
		f.append("Bin:%s" % bin.name)
	f.append("%s" % ProBin.BinStatuses[int(bin.status)])
	message = " ".join(f)
	authutil.log(eventtypes.RATTBE_LOGEVENT_PROSTORE_NOTICE_SENT.id,member_id=member_id,message=message,doneby=current_user.id,commit=commit)

notice_text = {
	"pastDue" : "Your membership payment is past-due, likely as a result of a payment card being expired or declined. Please go to http://join.makeitlabs.com/account to correct this situation.",
	"recentExpire" : "Your MakeIt Labs membership has expired or been canceled. If this was in error, please go to http://join.makeitlabs.com/account to correct this situation immedaitley, as your lab access has been disabled.\n\nIf this was intentional, we hope to see you back someday! You may re-activate your membership at a later time through the link above. (This will re-activate your existing key fob, and will restore access and privileges automatically, without having to redo orientations, waivers, and any equipment authorization you have may have.)",
	"gracePeriod" : "Your MakeIt Labs membership has recently expired or been canceled. You are currently still in a grace period in which you can correct. Please go to http://join.makeitlabs.com/account to correct this situation immedaitley, or your lab access has will be disabled.",
	"NoWaiver" : """We do not have a \"Member Waiver\" on file. To avoid issues with your membership or lab access, please go to https://www.smartwaiver.com/v/makeitlabs please make sure to enter the following EXACTLY as shown:

  email: {email}
  First Name: {firstname}
  Last Name: {lastname}
""",
	"ProBinNoWaiver" : """We do not have your \"Pro-Storage Waiver\" on file. (This is different/seperate from standard membership waiver). Please execute this waiver immediatley at http://smartwaiver.com/blah. To avoid further delay, please make sure to enter the following EXACTLY as shown:

  email: {email}
  First Name: {firstname}
  Last Name: {lastname}
""",
	"Subscription" : """There is a problem with your subscription payment. This could be that you have canceled your account, or another problem processing your payment, such as the card on file has expired. Please rectfy by going to the following:

http://join.makeitlabs.com/account
""",
	"ProBin_notInUse" : "Your Pro storage bin is listed as \"Not In Use\". Please clarify if you are using it so we can set the record straight.",
	"ProBin_discarded" : "Your Pro storage bin is listed as having possibly been missing or discarded.",
	"ProBin_gracePeriod" : "Your should have received a prior notice about your Pro storage bin. You may need to either collect your belongings, or fix your membership",
	"ProBin_forefeited" : "Your Pro storage bin has been forfitted. Please collect your belongings and notify us when you have vacated the bin.",
	"ProBin_moved" : "Your Pro storage bin has been forefited, but you have not removed your belongings. The bin with your materials has been moved elsewhere to re-purpose this storage locations. Please contact us to collect your belongins. Failure to do so will result in loss of property.",
	"ProBin_donated" : "You have not collected items left in your forfitted storage bin. Persuiant to MakeIt Labs rules, these items have either been discarded, or donated to the lab."
}

notice_header = """
This is an automated message about in issue with your MakeIt Labs Membership. Please attend to immediately to avoid property loss, access loss or revocation of storage or membership privileges.
"""

notice_footer = """
For any other questions or assistance with this matter, please email borad@makeitlabs.com
"""
# Send notices to members
def sendnotices(bin_id,notices):
	err=0
	no = notices.split()
	bin = ProBin.query.filter(ProBin.id == bin_id)
	bin = bin.outerjoin(ProLocation).add_column(ProLocation.location).one()
	member = Member.query.filter(Member.id == bin.ProBin.member_id).one()
	print member.member,member.email,member.alt_email,no,bin.location,bin.ProBin.name
	text=notice_header
	text += "\n"
	for n in no:
		if n in notice_text:
			text  += notice_text[n]
		else:
			text += "Unexpected notice: %s" %n
		text += "\n"
	if len(no) == 0:
		text += "There are NO issues with your Pro-Storage Bin. Everything is awesome! :)\n"

	text+=notice_footer

	text=text.format(firstname=member.firstname,lastname=member.lastname,email=member.email,location=bin.location)

	print "SEND TO",member.email,member.alt_email
	print text
	print
	print
	try:
		genericEmailSender("info@makeitlabs.com",member.email,"Your MakeIt Labs Pro-Storage Bin",text)
		genericEmailSender("info@makeitlabs.com",member.alt_email,"Your MakeIt Labs Pro-Storage Bin",text)
		authutil.log(eventtypes.RATTBE_LOGEVENT_PROSTORE_NOTICE_SENT.id,member_id=member.id,message=notices,doneby=current_user.id,commit=0)
	except BaseException as e:
		err=1
		logger.error("Failed to send Pro-Storage email: "+str(e))
	db.session.commit()
	return err

def addtag(memberNotice,m,tag):
	if m.member not in memberNotice:
		memberNotice[m.member]={'notices':[],
			'keys': {
				'firstname':m.firstname,
				'lastname':m.lastname,
				'email':m.alt_email
			}
		}
	memberNotice[m.member]['notices'].append(tag)
	
def notices():
	memberNotice={}
	res = db.session.query(Member.member,Member.firstname,Member.lastname,Member.alt_email,Member.id)
	res = res.outerjoin(Subscription,Subscription.member_id == Member.id)
	res = addQuickAccessQuery(res)
	res = res.add_column(Subscription.active.label("active_2"))
	res = res.add_column(Subscription.expires_date)

	# Add Main Waiver Count
	sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("waiverCount")).group_by(Waiver.member_id)
	sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_MEMBER)
	sq = sq.subquery()
	res = res.add_column(sq.c.waiverCount.label("memberWaivers")).outerjoin(sq,(sq.c.member_id == Member.id))

	# Add ProStore Waiver Count
	sq = db.session.query(Waiver.member_id,func.count(Waiver.member_id).label("prostoreWaiverCount")).group_by(Waiver.member_id)
	sq = sq.filter(Waiver.waivertype == Waiver.WAIVER_TYPE_PROSTORE)
	sq = sq.subquery()
	res = res.add_column(sq.c.prostoreWaiverCount.label("prostoreWaivers")).outerjoin(sq,(sq.c.member_id == Member.id))

	# Add Bin Count
	sq = db.session.query(ProBin.member_id,func.count(ProBin.member_id).label("binCount")).group_by(ProBin.member_id)
	sq = sq.subquery()
	res = res.add_column(sq.c.binCount.label("proBinCount")).outerjoin(sq,(sq.c.member_id == Member.id))

	members = res.all()

	for m in members:
		print m
		if m.active == 'Grace Period':
			addtag(memberNotice,m,"gracePeriod")
		if m.active == 'Recent Expire':
			expireddays = datetime.now() - m.expires_date
			exp_days = int(expireddays.total_seconds()/(24*3600))
			if (exp_days <= 30):
				addtag(memberNotice,m,"recentExpire") # TODO Add time cap?
		if m.proBinCount and not m.prostoreWaivers:
			addtag(memberNotice,m,"ProBinNoWaiver") 
		if m.active_2 == "false (past_due)":
			addtag(memberNotice,m,"pastDue") 

		if m.proBinCount:
			# Need to make sure ProStore waiver is ok
			# Then we need to check status of each, individual bin
			for b in ProBin.query.filter(ProBin.member_id == m.id).outerjoin(ProLocation).add_column(ProLocation.location).all():
				if b.ProBin.status != ProBin.BINSTATUS_IN_USE:
					addtag(memberNotice,m,"ProBin_%s:%s" % (ProBin.BinShortCodes[b.ProBin.status],b.location)) 
					
			print m,"WAIVERS:",m.memberWaivers,"Bins",m.proBinCount,"BinWaiver",m.prostoreWaivers

	# SEND NOTICES
	for n in memberNotice:
		print n,memberNotice[n]
		for x in memberNotice[n]['notices']:
			if x in notice_text:
				print "  ",notice_text[x].format(**memberNotice[n]['keys'])
			else:
				print "  ",("\"%s\" -- yeah, we don't know what that means, but it looks like a problem." % x)
			

def cli_member_notices(cmd,**kwargs):
	notices()
	
