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
import subprocess
import os
import inspect
from google import genai
#from .. import requireauth as requireauth
from .. import utilities as authutil
from ..utilities import _safestr as safestr
from authlibs import eventtypes
from authlibs import payments as pay
from sqlalchemy import case, DateTime, text, inspect as sql_inspect
from datetime import datetime

import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("reports", __name__, template_folder='templates', static_folder="static",url_prefix="/reports")

# ------------------------------------------------------------
# Reporting controllers
# ------------------------------------------------------------

@blueprint.route('/oldreports', methods=['GET'])
@roles_required(['Admin','Finance','Useredit'])
@login_required
def oldreports():
    """(Controller) Display some pre-defined report options"""
    stats = {} #getDataDiscrepancies()
    return render_template('oldreports.html',stats=stats)

@blueprint.route('/', methods=['GET'])
@roles_required(['Admin','Finance','Useredit'])
@login_required
def reports():
    """(Controller) Display some pre-defined report options"""
    return render_template('reports.html')

@blueprint.route('/bigbrain', methods=['GET'])
@roles_required(['Admin','Finance','Useredit'])
@login_required
def bigbrain_page():
    """(Controller) Display BigBrain AI query interface"""
    return render_template('ai_query.html')

@blueprint.route('/bigbrain', methods=['POST'])
@roles_required(['Admin','Finance','Useredit'])
@login_required
def bigbrain():
    """(Controller) Process BigBrain AI database query"""
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        if not question:
            return json.dumps({'status': 'error', 'message': 'Question is required'})
        
        # Initialize Google AI client
        api_key = current_app.config['globalConfig'].Config.get('GoogleAI', 'token', fallback='')
        
        if not api_key:
            return json.dumps({'status': 'error', 'message': 'Google AI API key not configured in config'})
        
        client = genai.Client(api_key=api_key)
        
        # Get database schema using SQLAlchemy
        schema = get_database_schema()
        
        # Generate SQL query
        sql = generate_sql_query(client, schema, question)
        
        # Execute SQL query
        result = execute_sql_query(sql)
        
        # Generate final report
        answer = generate_final_report(client, schema, sql, result, question)
        
        return json.dumps({
            'status': 'ok',
            'sql': sql,
            'answer': answer
        })
        
    except Exception as e:
        logger.error(f"AI query error: {e}")
        return json.dumps({'status': 'error', 'message': str(e)})

def get_database_schema():
    """Get database schema using subprocess like original g.py"""
    import subprocess
    
    try:
        # Use subprocess to get schema - paths are relative to project root now
        db1 = subprocess.check_output(["sqlite3","makeit.db",".schema"]).decode("utf-8")
        db2 = subprocess.check_output(["sqlite3","log.db",".schema"]).decode("utf-8")
        db3 = subprocess.check_output(["sqlite3","makeit.db","select id,name from tools"]).decode("utf-8")
        db4 = subprocess.check_output(["sqlite3","makeit.db","select id,name from resources"]).decode("utf-8")
        
        schema = f"""
TWO related databases - so remember that queries that use inter-related tables must specify which database!

First database called makeit.db:
{db1}

Second database called log.db:

{db2}

Try to resolve tool or resource names to these IDs as best you can - write queries to lookup against these rather than using names directly in queries:

tools defined as:
{db3}

resources defined as:
{db4}


"""
        return schema
        
    except Exception as e:
        logger.error(f"Error getting database schema: {e}")
        # Fallback to basic schema info
        return "Error retrieving database schema. Please check database connectivity."

def generate_sql_query(client, schema, question):
    """Generate SQL query using Google AI"""
    system = """
You are an automated database agent - return sqlite3 SQL only. 
Do not do anything to drop, modify add database at all. Never return more than 250 entries. Return error if trying to modify databases
Be sure to include:

    ATTACH DATABASE "makeit.db" as makeit;
    ATTACH DATABASE "log.db" as log;

Make sure each table reference uses the correct attached database!
return ONLY raw SQL - no block around it like triple-backtick clauses, etc.

You are ONLY to determine what SQL query you would need to execute to give yourself the data required to answer the user's question.
Take SPECIAL care when writing SQL queries, that any tables you reference above must be specified with a "makeit." or a "log." prefix, or the wrong database will be used.
"""

    
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        config=genai.types.GenerateContentConfig(
            system_instruction=system),
        contents=f"{schema}\n\nThe user's question is as follows: {question}",
    )
    
    #print (f"BigBrain SQL shoult be:\n{response.text.strip()}\n")
    return response.text.strip()

def execute_sql_query(sql):
    """Execute SQL query using subprocess for ATTACH DATABASE support"""
    import subprocess
    
    try:
        # Use subprocess like the original g.py to support ATTACH DATABASE
        result = subprocess.check_output(["sqlite3","-readonly","-json"], 
                                       input=sql.encode("utf-8")).decode("utf-8")
        #print (f"BigBrain SQL query returns:\n{result}\n")
        return result
            
    except Exception as e:
        logger.error(f"SQL execution error: {e}\nSQL: {sql}")
        return f"SQL Error: {str(e)}"

def generate_final_report(client, schema, sql, result, question):
    """Generate final HTML report using Google AI"""
    system = """
User has asked a question. We queried a bunch of data from our database in an attempt to provide an answer. Use the included data to help best answer question or generate report for the user. Provide full answer in HTML format. Do not put a leading "HTML" header/footer, as raw response must be embedded in existing HTML.
"""
    
    prompt=f"""
        We have two a databases with a schemas like:

        {schema}

        ...from which we issued the following query(s) to database:

        {sql}

        ...which obtained the following data/results from database:

        {result}

        Given this data, how would we answer the user's question, which is: 

        {question}

        Remember that right now it is {datetime.now()}, therefore data for the current time period will be incomplete and truncated.

        """,
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        config=genai.types.GenerateContentConfig(
            system_instruction=system),
        contents=prompt,
    )
    
    #print (f"BigBrain Final prompt:\n{prompt}\n<<END>>\n")
    return response.text.strip()


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

@blueprint.route('/active_members.csv', methods=['GET'])
@login_required
@roles_required(['Admin','Finance','Useredit'])
def active_members_csv():
    """Download active members list as CSV for external email systems or manual Google Groups import"""
    f = subprocess.Popen(
        ["./active_members.py", "--csv"],
        cwd="authlibs/reports/reports/",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout_data, stderr_data = f.communicate()
    if f.returncode != 0:
        err_msg = stderr_data.decode("utf-8", errors="replace").strip() or "Failed to generate CSV"
        return Response(err_msg, status=500, mimetype='text/plain')
    return Response(
        stdout_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=active_members.csv'}
    )

@blueprint.route('/runreport/<string:report>', methods=['GET'])
@login_required
@roles_required(['Admin','Finance','Useredit'])
def runreport(report):
    report = report.replace("/","")
    report = report.replace(".","")
    try:
        since_date = request.args.get('since', '')
        mode = request.args.get('mode', '').strip().lower()
        res = {
                "status": "ok",
                "text":f"This is a run of report {report}"
                }
        
        env = os.environ.copy()
        if since_date:
            env['REPORT_SINCE'] = since_date
        if mode in ('sync', 'csv'):
            env['REPORT_MODE'] = mode
            
        f = subprocess.Popen(["./"+report+".py"],cwd="authlibs/reports/reports/",stdout=subprocess.PIPE,stderr=subprocess.PIPE, env=env)
        txt = f.stdout.read().decode("utf-8")
        txt += f.stderr.read().decode("utf-8")
        result = f.wait()
        res['text']=txt + f"Result: {result}"
    except BaseException as e:
        res = {
                "status": "error",
                "text":f"BaseException {e}"
                }
    return (json.dumps(res,indent=2), 200, {'Content-type': 'application/json', 'Content-Language': 'en'})


def register_pages(app):
	app.register_blueprint(blueprint)
