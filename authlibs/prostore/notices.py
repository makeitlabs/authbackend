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
	"NoWaiver" : """We do not have your \"Pro-Storage Waiver\" on file. (This is different/seperate from standard membership waiver). Please execute this waiver immediatley at http://smartwaiver.com/blah. To avoid further delay, please make sure to enter the following EXACTLY as shown:

  email: {email}
  First Name: {firstname}
  Last Name: {lastname}
""",
	"Subscription" : """There is a problem with your subscription payment. This could be that you have canceled your account, or another problem processing your payment, such as the card on file has expired. Please rectfy by going to the following:

http://join.makeitlabs.com/account
""",
	"BinGone" : "Your bin is listed as \"gone\".",
	"Grace" : "Your should have received a prior notice about your Pro-Storage membership. You may need to either collect your belongings, or fix your membership",
	"Forefeit" : "Your Pro-Storage location has been forfitted. Please collect your belongings and notify us when you have vacated the bin.",
	"Moved" : "Your location has been forefited, but you have not removed your belongings. The bin with your materials has been moved elsewhere to re-purpose this storage locations. Please contact us to collect your belongins. Failure to do so will result in loss of property.",
	"Donated" : "You have not collected items left in your forfitted storage bin. Persuiant to MakeIt Labs rules, these items have either been discarded, or donated to the lab."
}

notice_header = """
This is an automated message about in issue with your MakeIt Lab Pro-Membership storage bin. Please attend to immediately to avoid property loss, access loss or revocation of storage or membership privileges.
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
	text+=notice_footer

	text=text.format(firstname=member.firstname,lastname=member.lastname,email=member.email)

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
