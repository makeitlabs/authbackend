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
        "NoWaiver" : """We do not have your \"Pro-Storage Waiver\" on file. (This is different/seperate from standard membership waiver). Please execute this waiver immediately at http://smartwaiver.com/v/prostoragebin  - To avoid further delay, please make sure to enter the following EXACTLY as shown:
  email: {email}
  First Name: {firstname}
  Last Name: {lastname}""",
        "Dup" : """You have more than one bin associagted with your member account. Pro members are entitled to one bin only. Please consolodate your storage to a single bin and notify \"board@makeitlabs.com\" with which bin you are keeping.
""",
    "Subscription" : """There is a problem with your subscription payment. This could be that you have canceled your account, or another problem processing your payment, such as the card on file has expired. Please rectify by going to the following url:

http://join.makeitlabs.com/account

""",
    "BinGone" : "Your bin is listed as \"gone\". Bins are property of MakeIt Labs, and should not be removed from the premises.",
    "NonPro" : "You are required to maintain a \"Pro\"-level memebership as a condition of retaining Storage Bin privilages. Please upgrade your membership or forefit your bin.",
    "Grace" : "Your should have received a prior notice about your Pro-Storage membership. You may need to either collect your belongings, or fix your membership.",
    "Forefeit" : "Your Pro-Storage location has been forfeited due to a lapse in membership. Please collect your belongings and notify us when you have vacated the bin.",
    "Moved" : "The bin with your materials has been moved. Please contact us to collect your belongings. Failure to do so will result in your bin contents being considered a donation to MakeIt Labs after 60 days from first notice.",
    "Donated" : "You have not collected items left in your forfeited storage bin. Pursuant to MakeIt Labs rules, these items have either been discarded, or donated to the lab."
}

notice_header = """
This is an automated message about in issue with your MakeIt Lab Pro-Membership storage bin (at location {location}). Please attend to immediately to avoid property loss, access loss or revocation of storage or membership privileges.
"""

notice_footer = """
For any other questions or assistance with this matter, please email board@makeitlabs.com
"""
# Send notices to members
def sendnotices(bin_id,notices,debugOnly=False):
    debug={}
    err=0
    no = notices.split()
    bin = ProBin.query.filter(ProBin.id == bin_id)
    bin = bin.outerjoin(ProLocation).add_column(ProLocation.location).one()
    member = Member.query.filter(Member.id == bin.ProBin.member_id).one()
    print (member.member,member.email,member.alt_email,no,bin.location,bin.ProBin.name)
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

    print ("SEND TO",member.email,member.alt_email)
    print (text)
    print ("")
    print ("")
    debug['text']=text
    debug['email']=member.email
    debug['altemail']=member.alt_email
    debug['bin_id']=bin_id
    debug['member']=member.member
    debug['location']=bin.location
    if not debugOnly:
        try:
            sendTo = f"{member.email}, {member.alt_email}"
            #genericEmailSender("info@makeitlabs.com",member.email,"Your MakeIt Labs Pro-Storage Bin",text)
            #genericEmailSender("info@makeitlabs.com",member.alt_email,"Your MakeIt Labs Pro-Storage Bin",text)
            genericEmailSender("info@makeitlabs.com",sendTo,"Your MakeIt Labs Pro-Storage Bin",text)
            authutil.log(eventtypes.RATTBE_LOGEVENT_PROSTORE_NOTICE_SENT.id,member_id=member.id,message=notices,doneby=current_user.id,commit=0)
        except BaseException as e:
            err=1
            logger.error("Failed to send Pro-Storage email: "+str(e))
        db.session.commit()
    return (err,debug)

