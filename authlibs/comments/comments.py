#vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, Resource, Tool, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs, Node
from functools import wraps
import json
#from .. import requireauth as requireauth
from .. import utilities as authutil
from ..utilities import _safestr as safestr
from ..utilities import _safeemail as safeemail
from authlibs import eventtypes

import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)

blueprint = Blueprint("comments", __name__, template_folder='templates', static_folder="static",url_prefix="/comments")



@blueprint.route('/', methods=['GET'])
@login_required
def comments():
	"""(Controller) Display Tools and controls"""
	comments = _get_comments()
	access = {}
	resources=Resource.query.all()
	nodes=Node.query.all()
	nodes.append(Node(id="None",name="UNASSINGED")) # TODO BUG This "None" match will break a non-sqlite3 database
	return render_template('comments.html',comments=comments,editable=True,tool={},resources=resources,nodes=nodes)

def get_comments(**kvargs):
		 mn=Member.query.all()
		 memc={}
		 for m in mn:
				memc[int(m.id)]=m.member
		 if 'member_id' in kvargs:
			 comments = Logs.query.filter(Logs.member_id == kvargs['member_id'])
		 if 'resource_id' in kvargs:
			 comments = Logs.query.filter(Logs.resource_id == kvargs['resource_id'])
		 if 'tool_id' in kvargs:
			 comments = Logs.query.filter(Logs.tool_id == kvargs['tool_id'])
		 if 'node_id' in kvargs:
			 comments = Logs.query.filter(Logs.node_id == kvargs['node_id'])
		 comments = comments.filter(Logs.event_type == eventtypes.RATTBE_LOGEVENT_COMMENT.id)
		 comments = comments.order_by(Logs.time_reported.desc())
		 comments = comments.all()

		 cc = []
		 for c in comments:
				done = "#"+str(c.doneby)
				if int(c.doneby) in memc:
					done=memc[int(c.doneby)]
				cc.append({'when':c.time_reported,'doneby':done,'comment':c.message})
		 return cc


""" Permissions here get strange, becuase comments get granuar dependin on what's being commented on
		We don't have to go crazy, though - they're just comments after all - and everything is inherently
		tagged with the poster, anyway. For now, we'll just require the user to at least be logged-in,
		and let the GUI do most of the filtering. 

		TODO we can get more picky if we ever really care later...
"""
@blueprint.route('/', methods=['POST'])
@login_required
def add_comment():
	"""(Controller) Display Tools and controls"""
	c = Logs(doneby=current_user.id,message=request.form['comment'],event_type = eventtypes.RATTBE_LOGEVENT_COMMENT.id)
	if current_user.privs('RATT'):
		if 'resource_id' in request.form:
			c.resource_id = int(request.form['resource_id'])
		if 'tool_id' in request.form:
			c.tool_id = int(request.form['tool_id'])
		if 'node_id' in request.form:
			c.node_id = int(request.form['node_id'])
	if current_user.privs('Useredit') or current_user.privs('Finance'):
		if 'member_id' in request.form:
			c.member_id = int(request.form['member_id'])
	db.session.add(c)
	db.session.commit()
	flash("Comment Added")
	return redirect(request.form['redirect'])

def register_pages(app):
	app.register_blueprint(blueprint)
