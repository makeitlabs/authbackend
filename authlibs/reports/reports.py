# vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, Resource, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs, ApiKey, Blacklist
from functools import wraps
import json
#from .. import requireauth as requireauth
from .. import utilities as authutil
from ..utilities import _safestr as safestr
from authlibs import eventtypes
from authlibs import payments as pay
from sqlalchemy import case, DateTime

import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("reports", __name__, template_folder='templates', static_folder="static",url_prefix="/reports")

# ------------------------------------------------------------
# Reporting controllers
# ------------------------------------------------------------

@blueprint.route('/', methods=['GET'])
@login_required
def reports():
    """(Controller) Display some pre-defined report options"""
    stats = {} #getDataDiscrepancies()
    return render_template('reports.html',stats=stats)

# Not used right now - I think it is exclusivley old "pinpayments" stuff??
def getDataDiscrepancies():
    """Extract some commonly used statistics about data not matching"""
    # Note" SQLLIte does not support full outer joins, so we have some duplication of effort...
    stats = {}
    sqlstr = """select m.member,m.active,m.plan,p.expires_date,p.updated_date from members m
            left outer join payments p on p.member=m.member where p.member is null order by m.member"""
    stats['members_nopayments'] = db.session.execute(sqlstr)
    sqlstr = """select p.member,p.email,a.member from payments p left outer join accessbymember a
            on p.member=a.member where a.member is null and p.expires_date > Datetime('now') order by p.member"""
    stats['paid_noaccess'] = query_db(sqlstr)
    sqlstr = """select p.member,m.member from payments p left outer join members m on p.member=m.member
        where m.member is null"""
    stats['payments_nomembers'] = query_db(sqlstr)
    sqlstr = """select a.member from accessbymember a left outer join members m on a.member=m.member
            where m.member is null and a.member is not null group by a.member"""
    stats['access_nomembers'] = query_db(sqlstr)
    sqlstr = """select distinct(resource) as resource from accessbymember where resource not in (select name from resources)"""
    stats['access_noresource'] = query_db(sqlstr)
    sqlstr = "select DISTINCT(member) from tags_by_member where member not in (select member from members) order by member"
    stats['tags_nomembers'] = query_db(sqlstr)
    sqlstr = """select DISTINCT(a.member), p.expires_date from accessbymember a join payments p on a.member=p.member where
            p.expires_date < Datetime('now')"""
    stats['access_expired'] = query_db(sqlstr)
    sqlstr = """select member,expires_date from payments where expires_date > Datetime('now','-60 days')
                and expires_date < Datetime('now')"""
    stats['recently_expired'] = query_db(sqlstr)
    sqlstr = "select member,expires_date,customerid,count(*) from payments group by member having count(*) > 1"
    stats['duplicate_payments'] = query_db(sqlstr)
    return stats

# ------------------------------------------------------------
# Blacklist entries
# - Ignore bad pinpayments records, mainly
# ------------------------------------------------------------

@blueprint.route('/blacklist', methods=['GET'])
@login_required
@roles_required(['Admin','Finance'])
def blacklist():
    """(Controller) Show all the Blacklist entries"""
    #    sqlstr = "select entry,entrytype,reason,updated_date from blacklist"
    #blacklist = db.session.execute(sqlstr)
    blacklist = Blacklist.query.all()
    return render_template('blacklist.html',blacklist=blacklist)


def register_pages(app):
	app.register_blueprint(blueprint)
