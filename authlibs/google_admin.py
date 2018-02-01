##!/usr/bin/env python
""" Utilities for handling Google SDK functions

Commonly used functions:

searchEmail - Check for a firstname.lastname@makeitlabs.com user
searchUser - Check for a name String (assumes string is a prefix, not a substring)
createUser - Create a new user in the MakeItLabs.com domain
sendWelcomeEmail - Send the welcome note.

TODO:
- Proper logging and improced error handling
- More self-tests
- Input validation, just in case.
- Move all pre-made strings to INI file
"""

import json

from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials
from apiclient import discovery
from apiclient import errors
from email.mime.text import MIMEText
import base64

import logging
logger = logging.getLogger(__name__)

# Settings
SCOPES = ['https://www.googleapis.com/auth/admin.directory.user.readonly','https://www.googleapis.com/auth/admin.directory.user','https://www.googleapis.com/auth/gmail.compose']
KEYFILE = 'makeitlabs.json'
EMAIL_USER = 'makeitlabs.automation@makeitlabs.com'
ADMIN_USER = 'bill.schongar@makeitlabs.com'
TEST_EMAIL = 'bill.schongar@makeitlabs.com'
DOMAIN = "makeitlabs.com"

def searchEmail(emailstr):
    """Search for a specific email address in the DOMAIN domain"""
    service = _buildAdminService()
    query_str = "email:%s orgUnitPath=/" % emailstr
    results = service.users().list(domain=DOMAIN, maxResults=500,orderBy='email',query=query_str).execute()
    users = results.get('users', [])
    return users

def createUser(firstname,lastname,userid,alt_email,password,isTest=False):
    ### TODO - Make sure no special characters
    primary_email = "%s@makeitlabs.com" % (userid)
    userinfo = {'primaryEmail': primary_email,
            'name': { 'givenName': firstname, 'familyName': lastname },
            'emails': [
                {
                'address': primary_email,
                'primary': 'true'
                },
                {
                'address': alt_email,
                'primary': 'false'
                },
            ],
            'password': password,
    }
    logger.debug(userinfo)
    if isTest:
        logger.info("Test mode bypass - otherwise would create new Google Account for : %s (%s)" % (userid,alt_email))
    else:
        service = _buildAdminService()
        service.users().insert(body=userinfo).execute()
    return userid

def sendWelcomeEmail(username,password,email):
    logger.info("Sending welcome email to %s at %s" % (username,email))
    letter = "Welcome to MakeIt Labs, and thanks for signing up!\n\n As a new member you have been assigned a MakeIt Labs account: \n\n"
    letter += "\tUsername: %s \n" % username
    letter += "\tTemporary password: %s \n" % password
    letter += """

Here's some helpful information to get started:

1) How do I get into the building?
--
To gain access to the building, you'll need to have your RFID setup, sign the membership agreement, and go through orientation.  There is an orientation every Thursday at 7pm, but if you need to request another time just contact us at info@makeitlabs.com and we'll try to accommodate you.  Please remember that we are a 100% volunteer run organization, and people may not be immediately available.

2) How do I access Members-only content on the website?
--
Your MakeIt Labs account (<your_username>@makeitlabs.com) is how you can access the Members-only portion of our Website: http://members.makeitlabs.com

3) How will important announcements be sent to me?
--
Your <your_username>@makeitlabs.com email address is where we will send ALL OFFICIAL ANNOUNCEMENTS and communications. To log in just navigate to http://mail.google.com, enter that account and password, and you're in!

Note: If you don't plan to check your @makeitlabs.com email address frequently, please be sure to set up mail forwarding so you don't miss important announcements.

(Pro Tip: Setting up forwarding can be done from within your MakeIt labs inbox by selecting the gear in the top right, then selecting settings.  From there, please select Forwarding and POP/IMAP.  The top option in there is to add a forwarding address.)

4) How can I communicate with other members?
--
Slack is our primary discussion forum for members, and we strongly encourage you to join and participate.  To register for a slack account with MakeIt Labs (it's free!), please go to the following link.  https://makeitlabs.slack.com/signup

5) The account created for me has a weird/wrong name! What do I do?
--
Account names are auto-generated based on the name provided by the Payment provider (Pinpayments, Stripe, etc) but we can adjust them. Send an email to board@makeitlabs.com and we'll help sort it out.

6) How do I get other information?
--
We have a documentation site (Wiki) available here: http://wiki.makeitlabs.com with lots of information.

Classes are (normally) scheduled through Eventbrite and visible here: https://www.eventbrite.com/o/makeit-labs-1932299069

If you have any questions, please feel free to contact us at info@makeitlabs.com or come to any Open House for in-person help.

See you soon!

-The MakeIt Labs Team

(PS - This email is sent from an automated tool, please use "info@makeitlabs.com" for asking questions. Thanks!)
--
MakeIt Labs
25 Crown St
Nashua NH 03060
www.makeitlabs.com
NH's First and Largest Makerspace, a 501c3 non-profit organization
"""
    service = _buildEmailService()
    msg = _CreateMessage('info@makeitlabs.com',email,'Welcome to MakeIt Labs, new member!',letter)
    _SendMessage(service,'me',msg)
    
def testMessage():
    service = _buildEmailService()
    message_text = "To: %s\r\nFrom: info@makeitlabs.com\r\nSubject: Test message for new member signup \r\n\r\nbody goes here with actual content. Hopefully this works?" % TEST_EMAIL
    try:
        message = (service.users().messages().send(userId='me', body={'raw': base64.urlsafe_b64encode(message_text)})
               .execute())
        #print 'Message Id: %s' % message['id']
        return message
    except errors.HttpError, err:
        print 'An error occurred: %s' % err

def _SendMessage(service, user_id, message):
  try:
    message = (service.users().messages().send(userId=user_id, body=message)
               .execute())
    #print 'Message Id: %s' % message['id']
    return message
  except errors.HttpError, err:
    print 'An error occurred: %s' % err
    
def _CreateMessage(sender, to, subject, message_text):
  """Create a formatted and properly encoded message for an email."""
  message = MIMEText(message_text)
  message['to'] = to
  message['From'] = "MakeIt Labs Infobot <%s>" % sender
  message['reply-to'] = 'info@makeitlabs.com'
  message['subject'] = subject
  return {'raw': base64.urlsafe_b64encode(message.as_string())}

def _buildEmailService():
    """Create an HTTP session specifically for the GMAIL API and sending emails from the EMAIL_USER account"""
    credentials = ServiceAccountCredentials.from_json_keyfile_name(KEYFILE, SCOPES)
    delegated_credentials = credentials.create_delegated(EMAIL_USER)
    http_auth = delegated_credentials.authorize(Http())
    service = discovery.build('gmail', 'v1', http=http_auth)
    return service

def _buildAdminService():
    """Create an HTTP session specifically for GOOGLE ADMIN SDK functions using ADMIN_USER"""
    credentials = ServiceAccountCredentials.from_json_keyfile_name(KEYFILE, SCOPES)
    delegated_credentials = credentials.create_delegated(ADMIN_USER)
    http_auth = delegated_credentials.authorize(Http())
    service = discovery.build('admin', 'directory_v1', http=http_auth)
    return service
   
def testGoogle():
    """Test Admin SDK: Grab a list of all users"""
    service = _buildAdminService()
    results = service.users().list(domain=DOMAIN, maxResults=500,orderBy='email').execute()
    users = results.get('users', [])
    print users

if __name__ == "__main__":
    #testGoogle()
    sendWelcomeEmail(user,password,email)
