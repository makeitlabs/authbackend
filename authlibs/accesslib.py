"""
vim:tabstop=2:expandtab

Library for access-related functions to be used throughout 

"""

import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from db_models import Member, db, Resource, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs, ApiKey, Node, NodeConfig, KVopt, Tool
from functools import wraps
import json
from authlibs import eventtypes
from authlibs import utilities as authutil
from json import dumps as json_dump

import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)
from sqlalchemy import case, DateTime


###
## ACL HANDLERS
###


# Since SQLalchemy returns complex query results as a list of
# tuples in separate columns - we put these columns into a
# meaningful dictionary for easier handling. If you change
# the results of this query - change this function!
def accessQueryToDict(y):
        x = y[1:] # Get rid of the first parameter - which is a MemberTag record
        return {
            'tag_ident':x[0],
            'plan':x[1],
            'nickname':x[2],
            'enabled':x[3],
            'reason':x[4],
            'allowed':x[5],
            'past_due':x[6],
            'grace_period':x[7],
            'expires_soon':x[8],
            'level':x[9],
            'member':x[10],
            'lockout_reason':x[11],
            'member_id':x[12],
            'membership':x[13],
            'expires_date':x[14],
            'last_accessed':"" # We may never want to report this for many reasons
            }

# Get all the users of a given resource
def _getResourceUsers(resource):
    """Given a Resource, return all users, their tags, and whether they are allowed or denied for the resource"""
    # Also provides some basic logic on various date fields to simplify later processing
    # - this could be done with raw calcs on the dates, if future editors are less comfortable with the SQL syntaxes used
	# Note: The final left join is to account for "max(expires_date)" equivalence without neededing a subquery
	# - yes, it's kind of odd, but it works


    rid = db.session.query(Resource.id).filter(Resource.name == resource)
    val = access_query(rid)

    # TEMP TODO - SQLalchemy returning set of tuples - turn into a dict for now
    result =[]
    for y in val:
        result.append(accessQueryToDict(y))

    # TODO Do we want to deal with adding people with implicit (Admin, RATT, HeadRM) permissions? This could be a LOT of extra queries

    return result

""" Pass this a record returned from an access_query() response
		Shall determine if access to a resource will be allowed

		"Resource text" generall comes from the database - it is a custom
		"access denined" message. If none, a boilerplate one will be returned

		returns a "false" or "allowed" string, and a warning message
"""
def determineAccess(u,resource_text):
        if not resource_text:
          resource_text = "You do not have access to this resource. See the Wiki for training information and resource manager contact info."

        c = {'board': "Contact board@makeitlabs.com with any questions.",
             'resource': resource_text}

        warning = ""
        allowed = u['allowed']
        # BKG TODO WARNING I added this first check to see if we had a valid sub

        if not u['membership']:
            warning = "You do not have a current subscription. Check your payment plan. %s" % (c['board'])
            allowed = 'false'
        elif u['past_due'] == 'true':
            if 'expires_date' in u:
                warning = "Your membership expired (%s) and the grace period for access has ended. %s" % (u['expires_date'],c['board'])
            else:
                warning = "Membership Past due - no expiration date"
            allowed = 'false'
        elif u['enabled'] == 0:
            if u['reason'] is not None:
                # This indicates an authorized admin has a specific reason for denying access to ALL resources
                warning = "This account has been disabled for a specific reason: %s. %s" % (u['reason'],c['board'])
            else:
                warning = "This account is not enabled. It may be newly added and not have a waiver on file. %s" % c['board']
            allowed = 'false'
        elif u['lockout_reason'] is not None:
            warning = u['lockout_reason']
            allowed = 'false'
        elif u['allowed'] == 'denied':
                warning = c['resource']
        elif u['grace_period'] == 'true':
            warning = """Your membership expired (%s) and you are in the temporary grace period. Correct this
            as soon as possible or you will lose all access! %s""" % (u['expires_date'],c['board'])
        return (warning,allowed)

# Main entry to fetch an Access Control List for a given resource
# containing disposition for this resource for ALL tags in the system
# The final data is somewhat specific to the ACL APIs, though the actual
# format in which it is conveyed on the wire is left to the caller
def getAccessControlList(resource):
    """Given a Resource, return what tags/users can/cannot access a reource and why as a JSON structure"""
    users = _getResourceUsers(resource)
    jsonarr = []
    resource_text=None
    reeource_url=None
    resource_rec = Resource.query.filter(Resource.name==resource).first()
    if resource_rec and resource_rec.info_text:
        resource_text = resource_rec.info_text
    if resource_rec and resource_rec.info_url:
        resource_url = resource_rec.info_url

    for u in users:
        (warning,allowed) = determineAccess(u,resource_text)
        hashed_tag_id = authutil.hash_rfid(u['tag_ident'])
        jsonarr.append({'tagid':hashed_tag_id,'tag_ident':u['tag_ident'],'allowed':allowed,'warning':warning,'member':u['member'],'nickname':u['nickname'],'plan':u['plan'],'last_accessed':u['last_accessed'],'level':u['level'],'raw_tag_id':u['tag_ident']})
    return json_dump(jsonarr,indent=2)

""" This is probably NOT the function you are looking for.
    it is used to ADD access check functions to a query you
    are defining elsewhere - so we can keep the logic for this
    in one common place
"""
def addQuickAccessQuery(query):
  query = query.add_column(case([
          ((Subscription.expires_date  == None), 'No Subscription'),
          ((Member.access_enabled ==0) , 'Access Disabled'),
          ((Subscription.expires_date > db.func.DateTime('now',"-1 day")), 'Active'),
          ((Subscription.expires_date > db.func.DateTime('now','-14 days')), 'Grace Period'),
          ((Subscription.expires_date > db.func.DateTime('now','-45 days')), 'Recent Expire'),
          ], else_ = 'Expired').label('active'))
  return query
def quickSubscriptionCheck(member=None,member_id=None):
  if not member_id:
          member_id = Member.query.filter(Member.member==member).one().id

  res = Subscription.query.filter(Subscription.member_id == member_id)

  res = addQuickAccessQuery(res)
  res = res.first()

  if not res: return 'No Subscription'

  return res[1]

""" This is the ONE AND ONLY query used for ACL checks 
		It is designed to run a few differnet ways.

		With "tags=True" and a resource_id specified, it will
		return records for ALL tags in the system - allong with
		their validity, and info on their member and subscription

		With "tags=False", it will serve as a vailidy check for
		a given user on a given resource. (i.e. Return a single
		record - independent of any tags).

		This function only RETURNS the query, it does not EXECUTE it,
		because different callers might want to handle it different
		ways (i.e. "all", "one", etc).

		The caller will also want to end the results of each record
		trhough accessQueryToDict() to turn it from a crazy list
		into a coherent dictionary. IF YOU CHANGE any of the
		returned results, change accessQueryToDict!!

		The results of EACH accessQueryToDict (if more than one)
		should then be parsed by "determineAccess()" (above) which
		contains the ligher logic to determine if access should be
		granted, and what warnings/error should be returned.

		BIGQUERY
"""
def access_query(resource_id,member_id=None,tags=True):
    if tags:
      q = db.session.query(MemberTag,MemberTag.tag_ident)
    else:
      q = db.session.query(Member,"''") 
    q = q.add_columns(Member.plan,Member.nickname,Member.access_enabled,Member.access_reason)
    q = q.add_column(case([(AccessByMember.resource_id !=  None, 'allowed')], else_ = 'denied').label('allowed'))
    # TODO Disable user it no subscription at all??? Only with other "plantype" logic to figure out "free" memberships
    q = q.add_column(case([((Subscription.expires_date < db.func.DateTime('now','-14 days')), 'true')], else_ = 'false').label('past_due'))
    q = q.add_column(case([((Subscription.expires_date < db.func.DateTime('now') & (Subscription.expires_date > db.func.DateTime('now','-13 day'))), 'true')], else_ = 'false').label('grace_period'))
    q = q.add_column(case([(Subscription.expires_date < db.func.DateTime('now','+2 days'), 'true')], else_ = 'false').label('expires_soon'))
    q = q.add_column(case([(AccessByMember.level != None , AccessByMember.level )], else_ = 0).label('level'))
    q = q.add_column(Member.member)
    q = q.add_column(AccessByMember.lockout_reason)

    # BKG DEBUG LINES 
    if (tags):
      q = q.add_column(MemberTag.member_id)
    else:
      q = q.add_column(AccessByMember.id)
    q = q.add_column(Subscription.membership)
    q = q.add_column(Subscription.expires_date)
    # BKG DEBUG ITEMS

    if (tags):
        q = q.outerjoin(Member,Member.id == MemberTag.member_id)
        if member_id:
            q = q.filter(MemberTag.member_id == member_id)
        if resource_id:
            q = q.outerjoin(AccessByMember, ((AccessByMember.member_id == MemberTag.member_id) & (AccessByMember.resource_id == resource_id)))
        else:
            q = q.outerjoin(AccessByMember, (AccessByMember.member_id == MemberTag.member_id))
    else: # No tags
        if member_id:
            q = q.filter(Member.id == member_id)
        if resource_id and member_id:
            q = q.join(AccessByMember, ((AccessByMember.resource_id == resource_id) & (AccessByMember.member_id == member_id)))

        elif resource_id:
            q = q.join(AccessByMember, (AccessByMember.resource_id == resource_id))
        elif member_id:
            q = q.outerjoin(AccessByMember, (AccessByMember.member_id == member_id))

    q = q.outerjoin(Subscription, Subscription.member_id == Member.id)
    if (tags):
      q = q.group_by(MemberTag.tag_ident)

    return q
    
# Does this user have the ability to do ANY kind of authorization in the system?
# Level is the minimum level allowed. So "1" = TRAINER - meaning can do any authorization
# 2 = ARM would mean can do some RM functions
def user_is_authorizor(member,member_id=None,level=1):
    if member_id:
      member=Member.query.filter(Member.id == member_id).one().id
    return (member.privs('HeadRM')) or (AccessByMember.query.filter(AccessByMember.member_id == member.id).filter(AccessByMember.level >= level).count() > 0)

# What privs do we have on this resource?
def user_privs_on_resource(member=None,member_id=None,resource=None,resource_id=None):
  if member_id:
    member=Member.query.filter(Member.id == member_id).one().id
  if resource_id:
    resource=Resource.query.filter(Resource.id == resource_id).one().id

  if (member.privs('HeadRM','RATT')):
    return AccessByMember.LEVEL_ADMIN

  q = AccessByMember.query.filter(AccessByMember.resource_id == resource.id)
  q = q.filter(AccessByMember.member_id == member.id).one_or_none()
  if not q:
    return AccessByMember.LEVEL_NOACCESS

  return q.level
