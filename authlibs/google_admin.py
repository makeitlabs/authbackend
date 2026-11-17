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
import os
import re
import datetime
import pytz
from dateutil import parser
from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials
try:
    from apiclient import discovery
    from apiclient import errors
except:
    from googleapiclient import discovery
    from googleapiclient import errors
from email.mime.text import MIMEText
import base64

import logging
logger = logging.getLogger(__name__)

# Scopes set in https://admin.google.com/ac/owl/domainwidedelegation
SCOPES = ['https://www.googleapis.com/auth/admin.directory.user.readonly','https://www.googleapis.com/auth/admin.directory.user',
        'https://www.googleapis.com/auth/gmail.compose','https://www.googleapis.com/auth/admin.directory.resource.calendar',
        'https://www.googleapis.com/auth/gmail.settings.basic',
        'https://www.googleapis.com/auth/gmail.settings.sharing']
KEYFILE = 'makeitlabs.json'
EMAIL_USER = 'makeitlabs.automation@makeitlabs.com'
ADMIN_USER = 'bill.schongar@makeitlabs.com'
TEST_EMAIL = 'bill.schongar@makeitlabs.com'
DOMAIN = "makeitlabs.com"
# Kept separate from SCOPES so existing functions are unaffected until
# admin.directory.group.member is authorized in Domain-Wide Delegation.
GROUP_SCOPES = ['https://www.googleapis.com/auth/admin.directory.group.member']
ACTIVE_MEMBERS_GROUP = 'active@makeitlabs.com'

def _get_keyfile_path():
    """Return path to KEYFILE, checking cwd first then repo root."""
    if os.path.exists(KEYFILE):
        return KEYFILE
    repo_root_keyfile = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', KEYFILE))
    if os.path.exists(repo_root_keyfile):
        return repo_root_keyfile
    return KEYFILE

def searchEmail(emailstr):
    #return ([])
    """Search for a specific email address in the DOMAIN domain"""
    service = _buildAdminService()
    query_str = "email:%s orgUnitPath=/" % emailstr
    results = service.users().list(domain=DOMAIN, maxResults=500,orderBy='email',query=query_str).execute()
    users = results.get('users', [])
    return users

def createUser(firstname,lastname,userid,alt_email,password,isTest=False):
    from . import utilities
    firstname = utilities.sanitize_name(firstname) or "Member"
    lastname = utilities.sanitize_name(lastname) or firstname
    userid = utilities.sanitize_userid(userid)
    if not userid:
        userid = utilities.make_member_id(firstname, lastname)
    if not userid:
        raise ValueError("Cannot create Google user: empty userid after sanitization")
    alt_email = alt_email.strip() if alt_email else ""
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

def _buildUserGmailService(user_email):
    """Create a Gmail API service delegated to act as a specific domain user.
    Used for managing per-user Gmail settings like forwarding.
    Uses google.oauth2 (newer library) with with_subject() for delegation,
    which is required for Gmail settings APIs on behalf of a user.
    Note: Gmail may not be ready immediately after account creation —
    callers should delay/retry if they get authorization errors."""
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(_get_keyfile_path(), scopes=SCOPES)
    delegated_creds = creds.with_subject(user_email)
    service = discovery.build('gmail', 'v1', credentials=delegated_creds)
    return service

def setupEmailForwarding(makeitlabs_email, forward_to_email):
    """Set up email forwarding on a makeitlabs.com Gmail account by creating
    a filter that matches all incoming mail and forwards it to the member's
    personal email address.

    Uses the Gmail Filters API instead of the autoForwarding endpoint.
    Filters created via service account delegation bypass the verification
    requirement, so forwarding works immediately without the target user
    needing to click a confirmation link.
    
    Requires two steps:
    1. Register the forwarding address (even if it won't be verified, Gmail requires it to exist).
    2. Create the filter.

    Mail is still delivered to the makeitlabs inbox (filters forward a copy).
    """
    makeitlabs_email = makeitlabs_email.strip()
    forward_to_email = forward_to_email.strip()
    logger.info("Setting up email forwarding: %s -> %s" % (makeitlabs_email, forward_to_email))

    service = _buildUserGmailService(makeitlabs_email)

    # Step 1: Register the forwarding address
    fwd_body = {'forwardingEmail': forward_to_email}
    try:
        service.users().settings().forwardingAddresses().create(
            userId='me', body=fwd_body
        ).execute()
        logger.info("Forwarding address registered for %s -> %s" %
                    (makeitlabs_email, forward_to_email))
    except errors.HttpError as e:
        if e.resp.status == 409:
            logger.info("Forwarding address already exists for %s -> %s (OK)" %
                        (makeitlabs_email, forward_to_email))
        else:
            raise

    # Step 2: Create a filter that matches all mail and forwards to the personal address
    filter_body = {
        'criteria': {
            'query': '*'
        },
        'action': {
            'forward': forward_to_email
        }
    }
    result = service.users().settings().filters().create(
        userId='me', body=filter_body
    ).execute()
    logger.info("Forwarding filter created for %s -> %s (filter id: %s)" %
                (makeitlabs_email, forward_to_email, result.get('id')))
    return True

def sendWelcomeEmail(username,password,email):
    email = email.strip() if email else email
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

6) Member Waiver

Save yourself some time by completing the MakeIt Labs Member Waiver before coming in for your orientation. Waiver can be found here: https://waiver.smartwaiver.com/w/5626bfb9a69fd/web/

7) How do I get other information?
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

def genericEmailSender(from_email,to_email,subject,contents):
    service = _buildEmailService()
    #if isinstance(contents, str): contents=contents.encode('utf-8')
    msg = _CreateMessage(from_email,to_email,subject,contents)
    _SendMessage(service,'me',msg)
    
def testMessage():
    service = _buildEmailService()
    message_text = "To: %s\r\nFrom: info@makeitlabs.com\r\nSubject: Test message for new member signup \r\n\r\nbody goes here with actual content. Hopefully this works?" % TEST_EMAIL
    try:
        message = (service.users().messages().send(userId='me', body={'raw': base64.urlsafe_b64encode(message_text).decode("utf-8")})
               .execute())
        #print 'Message Id: %s' % message['id']
        return message
    except errors.HttpError as  err:
        print ('An error occurred: %s' % err)

def _SendMessage(service, user_id, message):
  try:
    message = (service.users().messages().send(userId=user_id, body=message)
               .execute())
    #print 'Message Id: %s' % message['id']
    return message
  except errors.HttpError as err:
    print ('An error occurred: %s' % err)
    
def _CreateMessage(sender, to, subject, message_text):
  """Create a formatted and properly encoded message for an email."""
  message = MIMEText(message_text)
  message['to'] = to
  message['From'] = "MakeIt Labs Infobot <%s>" % sender
  message['reply-to'] = 'info@makeitlabs.com'
  message['subject'] = subject
  return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")}

def _buildEmailService():
    """Create an HTTP session specifically for the GMAIL API and sending emails from the EMAIL_USER account"""
    credentials = ServiceAccountCredentials.from_json_keyfile_name(_get_keyfile_path(), SCOPES)
    delegated_credentials = credentials.create_delegated(EMAIL_USER)
    http_auth = delegated_credentials.authorize(Http())
    service = discovery.build('gmail', 'v1', http=http_auth)
    return service

def _buildAdminService():
    """Create an HTTP session specifically for GOOGLE ADMIN SDK functions using ADMIN_USER"""
    credentials = ServiceAccountCredentials.from_json_keyfile_name(_get_keyfile_path(), SCOPES)
    delegated_credentials = credentials.create_delegated(ADMIN_USER)
    http_auth = delegated_credentials.authorize(Http())
    service = discovery.build('admin', 'directory_v1', http=http_auth)
    return service

def _buildGroupAdminService():
    """Create an Admin Directory API service delegated to ADMIN_USER for Google Group management."""
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(_get_keyfile_path(), scopes=GROUP_SCOPES)
    delegated_creds = creds.with_subject(ADMIN_USER)
    return discovery.build('admin', 'directory_v1', credentials=delegated_creds)

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

def _extract_google_api_error(err):
    """Extract a readable error message from a Google API HttpError or Exception."""
    if hasattr(err, 'content') and err.content:
        try:
            payload = json.loads(err.content.decode('utf-8'))
            msg = payload.get('error', {}).get('message')
            if msg:
                return msg
        except Exception:
            pass
    return str(err)

def syncGroupMembers(group_email, emails):
    """Add missing emails to a Google Group, skipping and reporting any invalid or errored emails.

    Returns a dict with keys:
      - group_email: target group address
      - existing_count: number of members already in the group before sync
      - already_present: list of emails already in the group
      - added: list of newly added emails
      - errors: list of dicts {'email': ..., 'error': ...} for skipped/failed emails
    """
    service = _buildGroupAdminService()

    existing_emails = set()
    page_token = None
    while True:
        results = service.members().list(
            groupKey=group_email,
            maxResults=200,
            pageToken=page_token
        ).execute()
        for member in results.get('members', []):
            addr = (member.get('email') or '').strip().lower()
            if addr:
                existing_emails.add(addr)
        page_token = results.get('nextPageToken')
        if not page_token:
            break

    existing_count = len(existing_emails)
    already_present = []
    added = []
    failed = []
    seen = set()

    for raw_email in emails:
        email = (raw_email or '').strip()
        if not email:
            continue
        email_lower = email.lower()
        if email_lower in seen:
            continue
        seen.add(email_lower)

        if not _EMAIL_RE.match(email):
            failed.append({'email': email, 'error': 'Invalid email format'})
            continue

        if email_lower in existing_emails:
            already_present.append(email)
            continue

        try:
            service.members().insert(
                groupKey=group_email,
                body={'email': email, 'role': 'MEMBER'}
            ).execute()
            added.append(email)
            existing_emails.add(email_lower)
        except errors.HttpError as err:
            status = getattr(getattr(err, 'resp', None), 'status', None)
            msg = _extract_google_api_error(err)
            if status == 409 or 'already exists' in msg.lower():
                already_present.append(email)
            else:
                failed.append({'email': email, 'error': msg})
        except Exception as err:
            failed.append({'email': email, 'error': str(err)})

    return {
        'group_email': group_email,
        'existing_count': existing_count,
        'already_present': already_present,
        'added': added,
        'errors': failed,
    }

def addToGoogleGroup(emails, group_email=ACTIVE_MEMBERS_GROUP):
    """Best-effort helper to add one or more emails to a Google Group.

    Never raises: any service, network, auth, or per-email error is logged and
    skipped so callers (e.g. member enrollment) are never interrupted.
    """
    added = []
    already_present = []
    failed = []

    if isinstance(emails, str):
        email_list = [emails]
    else:
        email_list = list(emails or [])

    try:
        service = _buildGroupAdminService()
    except Exception as err:
        logger.warning("Could not initialize Google Group service for %s: %s", group_email, err)
        return {'added': added, 'already_present': already_present, 'errors': [{'email': None, 'error': str(err)}]}

    seen = set()
    for raw_email in email_list:
        try:
            email = (raw_email or '').strip()
            if not email:
                continue
            email_lower = email.lower()
            if email_lower in seen:
                continue
            seen.add(email_lower)

            if not _EMAIL_RE.match(email):
                logger.warning("Skipping invalid email %r for Google Group %s", email, group_email)
                failed.append({'email': email, 'error': 'Invalid email format'})
                continue

            service.members().insert(
                groupKey=group_email,
                body={'email': email, 'role': 'MEMBER'}
            ).execute()
            logger.info("Added %s to Google Group %s", email, group_email)
            added.append(email)
        except errors.HttpError as err:
            status = getattr(getattr(err, 'resp', None), 'status', None)
            msg = _extract_google_api_error(err)
            if status == 409 or 'already exists' in msg.lower():
                already_present.append(email)
            else:
                logger.warning("Failed adding %s to Google Group %s (skipping): %s", email, group_email, msg)
                failed.append({'email': email, 'error': msg})
        except Exception as err:
            logger.warning("Unexpected error adding %r to Google Group %s (skipping): %s", raw_email, group_email, err)
            failed.append({'email': raw_email, 'error': str(err)})

    return {'added': added, 'already_present': already_present, 'errors': failed}
   
def get_event_time_reliable(event):
    """
    Extracts event times, converts them to the 'America/New_York' timezone,
    and then strips the timezone information, returning a naive datetime object.
    """
    start_info = event.get('start', {})
    end_info = event.get('end', {})

    NY_TZ = pytz.timezone('America/New_York')

    start_dt_naive = None
    end_dt_naive = None

    # --- 1. Handle Timed Events (DateTime) ---
    if 'dateTime' in start_info:
        # a. Parse and convert to NY timezone (result is timezone-aware)
        start_dt_aware_ny = parser.isoparse(start_info['dateTime']).astimezone(NY_TZ)
        end_dt_aware_ny = parser.isoparse(end_info['dateTime']).astimezone(NY_TZ)

        # b. Strip the timezone info to make it "naked" (naive)
        start_dt_naive = start_dt_aware_ny.replace(tzinfo=None)
        end_dt_naive = end_dt_aware_ny.replace(tzinfo=None)

    # --- 2. Handle All-Day Events (Date) ---
    elif 'date' in start_info:
        # All-day events start at midnight NY time.
        start_date = datetime.strptime(start_info['date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(end_info['date'], '%Y-%m-%d').date()

        # Combine with midnight, localize to NY (making it aware),
        # then strip the tzinfo to make it naive.

        start_dt_aware_ny = NY_TZ.localize(datetime.combine(start_date, datetime.min.time()))
        end_dt_aware_ny = NY_TZ.localize(datetime.combine(end_date, datetime.min.time()))

        start_dt_naive = start_dt_aware_ny.replace(tzinfo=None)
        end_dt_naive = end_dt_aware_ny.replace(tzinfo=None)

    return start_dt_naive, end_dt_naive

# Use the Calendar API scope for read/write access.
# If you only need read access, use: 'https://www.googleapis.com/auth/calendar.readonly'
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_API_NAME = 'calendar'
CALENDAR_API_VERSION = 'v3' # Standard version for Calendar API

# Your existing constants (KEYFILE, EMAIL_USER) remain the same

def _buildCalendarService(user_email_to_delegate_to):
    """
    Create an HTTP session specifically for the Google Calendar API
    delegated to act on behalf of a specific user in your domain.
    """
    # 1. Get credentials from the service account key file
    credentials = ServiceAccountCredentials.from_json_keyfile_name(_get_keyfile_path(), CALENDAR_SCOPES)

    # 2. Delegate authority to act as the target user (e.g., a domain user)
    delegated_credentials = credentials.create_delegated(user_email_to_delegate_to)

    # 3. Authorize the HTTP session
    http_auth = delegated_credentials.authorize(Http())

    # 4. Build the Calendar service object
    service = discovery.build(CALENDAR_API_NAME, CALENDAR_API_VERSION, http=http_auth)
    return service



def read_user_cal(email):
    calendar_service = _buildCalendarService(email)
    now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
    events_result = calendar_service.events().list(
        #calendarId='primary',  # The primary calendar of the delegated user
        calendarId=email,
        timeMin=now,
        maxResults=2,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])
    for event in events:
        print(event)

def calendar_read(email,resource):
    # The user you want to act on behalf of
    TARGET_USER_EMAIL = email
    RESOURCE_EMAIL = resource

    # 1. Build the service
    calendar_service = _buildCalendarService(TARGET_USER_EMAIL)

    # 2. Define the time range for the query
    now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time

    # 3. Call the events().list() method
    print(f"Fetching events for {TARGET_USER_EMAIL}...")
    events_result = calendar_service.events().list(
        #calendarId='primary',  # The primary calendar of the delegated user
        calendarId=RESOURCE_EMAIL,
        timeMin=now,
        maxResults=20,
        singleEvents=True,
        #creator=TARGET_USER_EMAIL,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    bookings = []
    if not events:
        print('No upcoming events found.')
    else:
        for event in events:
            isSelf = False
            isAccepted = False
            start = event['start'].get('dateTime', event['start'].get('date'))
            organizer_info = event.get('organizer', {})
            creator_info = event.get('creator', {})
            organizer_email = organizer_info.get('email', '')
            if 'self' in organizer_info: isSelf = organizer_info['self']
            if organizer_email.lower() == TARGET_USER_EMAIL.lower(): isSelf=True

            # Fallback to creator email if organizer is set to the resource email
            if organizer_email.lower() == RESOURCE_EMAIL.lower() and creator_info.get('email'):
                organizer_email = creator_info.get('email')
                if organizer_email.lower() == TARGET_USER_EMAIL.lower(): isSelf=True

            resourceCount=0
            start,end = get_event_time_reliable(event)
            for a in event.get('attendees', []):
                displayName = "<None>"
                responseStatus = "unknown"
                isResource = False
                if 'displayName' in a: displayName = a['displayName']
                if 'responseStatus' in a: responseStatus = a['responseStatus']
                if 'resource' in a: 
                    isResource= a['resource']
                    resourceCount += 1
                    if a['email'].lower() == RESOURCE_EMAIL.lower() and responseStatus == 'accepted':
                        isAccepted= True
            if (isAccepted):
                summary = event['summary'] if 'summary' in event else 'Reserved'
                booking = {
                        'calendar_id':event['id'],
                        'organizer_email':organizer_email,
                        'user':organizer_email, # REWRITE LATER
                        'isMine' : 1 if isSelf else 0,
                        'description' : summary,
                        'start':start.isoformat(),
                        'end':end.isoformat(),
                        }
                bookings.append(booking)
    return (bookings)


def delete_booking(user,event_id):
    calendar_service = _buildCalendarService(user)
    # Fetch the latest version of the event
    try:
        r = calendar_service.events().delete(
            calendarId='primary',
            eventId=event_id
        ).execute()
    except BaseException as e:
        print (f"DELETE CALENDAR FAILED - {user} {event_id}: {e}\n")
        return True

    print (f"Delete Calendar {event_id} OK\n")
    return False

def edit_booking(user,event_id,description,start,end,user_name=None):
    calendar_service = _buildCalendarService(user)

    if not user_name:
        local_part = user.split('@')[0]
        user_name = local_part.replace('.', ' ').title()

    clean_desc = (description or '').strip()
    if clean_desc and clean_desc.lower() != 'no description':
        summary = f"{user_name} - {clean_desc}"
    else:
        summary = f"{user_name} - Reserved"
        clean_desc = "None"

    event_body_desc = f"Reserved by: {user_name} ({user})\nNotes: {clean_desc}"

    patch = {
      'summary': summary,
      'description': event_body_desc,
      'start': {
        'dateTime': start.isoformat()
      },
      'end': {
        'dateTime': end.isoformat()
      },
     }

    try:
        updated_event = calendar_service.events().patch(
            calendarId='primary',
            eventId=event_id,
            body=patch,
            sendNotifications=True
        ).execute()
    except BaseException as e:
        print (f"Delete Calendar failed - {user} {event_id}: {e}\n")
        return (str(e))
    return None

def get_booking(user,event_id,resource):
    calendar_service = _buildCalendarService(user)
    # Fetch the latest version of the event
    updated_event = calendar_service.events().get(
        calendarId='primary',
        eventId=event_id
    ).execute()
    resource_status = 'unknown'

    event_id = updated_event['id']
    for attendee in updated_event.get('attendees', []):
        if attendee.get('email', '').lower() == resource.lower():
            resource_status = attendee.get('responseStatus', 'unknown')
            break
    return resource_status


def calendar_create(user,resource,description,start,end,user_name=None):
    # The user you want to act on behalf of
    TARGET_USER_EMAIL = user
    RESOURCE_EMAIL = resource

    if not user_name:
        local_part = user.split('@')[0]
        user_name = local_part.replace('.', ' ').title()

    clean_desc = (description or '').strip()
    if clean_desc and clean_desc.lower() != 'no description':
        summary = f"{user_name} - {clean_desc}"
    else:
        summary = f"{user_name} - Reserved"
        clean_desc = "None"

    event_body_desc = f"Reserved by: {user_name} ({user})\nNotes: {clean_desc}"

    # 1. Build the service
    calendar_service = _buildCalendarService(TARGET_USER_EMAIL)

    # 2. Define the event body (using RFC3339 format for datetime)
    event = {
      'summary': summary,
      'location': 'MakeIt Labs Reservation Portal',
      'organizer': {
          'email': user,
          'displayName': user_name,
          'self': True
          },
      'description': event_body_desc,
      'start': {
        'dateTime': start.isoformat()
      },
      'end': {
        'dateTime': end.isoformat()
      },
      'attendees': [
        {'email': RESOURCE_EMAIL, 'resource': True},
        {'email': user, 'displayName': user_name, 'responseStatus': 'accepted'}
      ],
    }

    # 3. Call the events().insert() method
    created_event = calendar_service.events().insert(
        calendarId='primary',
        body=event,
        sendNotifications=True  # Send email invitations to attendees
    ).execute()

    # 4. Check the resource's response status
    resource_status = 'unknown'

    event_id = created_event['id']
    for attendee in created_event.get('attendees', []):
        if attendee.get('email', '').lower() == RESOURCE_EMAIL.lower():
            resource_status = attendee.get('responseStatus', 'unknown')
            break
    # resource_status should be 'accepted'

    return event_id,resource_status

def getUsers():
    service = _buildAdminService()
    results = service.users().list(domain=DOMAIN, projection="custom",customFieldMask="Membership",query="email:bradley.goodman@makeitlabs.com", maxResults=1,orderBy='email').execute()
    users = results.get('users', [])
    print (users)

def testGoogle():
    """Test Admin SDK: Grab a list of all users"""
    service = _buildAdminService()
    results = service.users().list(domain=DOMAIN, maxResults=500,orderBy='email').execute()
    users = results.get('users', [])
    print (users)

if __name__ == "__main__":
    #testGoogle()
    #sendWelcomeEmail(user,password,email)
    #print (list_all_resource_emails(_buildAdminService()))
    #print (calendar_read("bradley.goodman@makeitlabs.com","makeitlabs.com_3133373236393938363631@resource.calendar.google.com"))
    print (delete_booking("bradley.goodman@makeitlabs.com","123"))
    #print (read_user_cal("bradley.goodman@makeitlabs.com"))
    #print (getUsers())
