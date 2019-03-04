#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs.comments import comments
from authlibs import accesslib

blueprint = Blueprint("tools", __name__, template_folder='templates', static_folder="static",url_prefix="/tools")



@blueprint.route('/', methods=['GET'])
@login_required
def tools():
	"""(Controller) Display Tools and controls"""
	tools = _get_tools()
	access = {}
	resources=Resource.query.all()
	nodes=Node.query.all()
	nodes.append(Node(id="None",name="UNASSINGED")) # TODO BUG This "None" match will break a non-sqlite3 database
	return render_template('tools.html',tools=tools,editable=True,tool={},resources=resources,nodes=nodes)

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def tools_create():
	"""(Controller) Create a tool from an HTML form POST"""
	r = Tool()
        r.name = (request.form['input_name'])
        # None handling shouldn't beneeded with new global form template
        if (request.form['input_node_id'] == "None"):
          r.node_id = None
        else:
          r.node_id = (request.form['input_node_id'])
        r.resource_id = (request.form['input_resource_id'])
        r.short = (request.form['input_short'])
        db.session.add(r)
        db.session.commit()
	flash("Created.")
	return redirect(url_for('tools.tools'))

@blueprint.route('/<string:tool>', methods=['GET'])
@login_required
def tools_show(tool):
	"""(Controller) Display information about a given tool"""
	r = Tool.query.filter(Tool.id==tool).one_or_none()
	if not r:
		flash("Tool not found")
		return redirect(url_for('tools.tools'))
	privs = accesslib.user_privs_on_resource(member=current_user,resource=r)
	readonly=False
	if (not current_user.privs('RATT')):
		readonly=True
	if privs < AccessByMember.LEVEL_ARM:
		flash("You don't have access to this")
		return redirect(url_for('index'))
	resources=Resource.query.all()
	nodes=Node.query.all()
	nodes.append(Node(id="None",name="UNASSINGED")) # TODO BUG This "None" match will break a non-sqlite3 database
	cc=comments.get_comments(tool_id=tool)

	tool_locked =  r.lockout is not None

	return render_template('tool_edit.html',rec=r,resources=resources,readonly=readonly,nodes=nodes,comments=cc,tool_locked=tool_locked)

@blueprint.route('/<string:tool>/lock', methods=['POST'])
@login_required
def tool_lock(tool):
	r = Tool.query.filter(Tool.id==tool).one_or_none()
	if not r:
		flash("Tool not found")
		return redirect(url_for('tools.tools'))
	if (not current_user.privs('RATT','HeadRM')) and (accesslib.user_privs_on_resource(resource=r,member=current_user)<AccessByMember.LEVEL_ARM):
		flash("You do not have privileges to lock out this tool")
		return redirect(url_for('tools.tools'))
		
	r.lockout=request.form['lockout_reason']
	authutil.log(eventtypes.RATTBE_LOGEVENT_TOOL_LOCKOUT_LOCKED.id,tool_id=r.id,message=r.lockout,doneby=current_user.id,commit=0)
	node = Node.query.filter(Node.id == r.node_id).one()
	authutil.send_tool_lockout(r.name,node.name,r.lockout)
	db.session.commit()
	flash("Tool is locked",'info')
	return redirect(url_for('tools.tools_show',tool=r.id))

@blueprint.route('/<string:tool>/unlock', methods=['POST'])
@login_required
def tool_unlock(tool):
	r = Tool.query.filter(Tool.id==tool).one_or_none()
	if not r:
		flash("Tool not found")
		return redirect(url_for('tools.tools'))

	if (not current_user.privs('RATT','HeadRM')) and (accesslib.user_privs_on_resource(resource=r,member=current_user)<AccessByMember.LEVEL_ARM):
		flash("You do not have privileges to unlock this tool")
		return redirect(url_for('tools.tools'))
		
	r.lockout=None
	authutil.log(eventtypes.RATTBE_LOGEVENT_TOOL_LOCKOUT_UNLOCKED.id,tool_id=r.id,doneby=current_user.id,commit=0)

	node = Node.query.filter(Node.id == r.node_id).one()
	authutil.send_tool_remove_lockout(r.name,node.name)
	flash("Tool is unlocked",'success')
	db.session.commit()
	return redirect(url_for('tools.tools_show',tool=r.id))

@blueprint.route('/<string:tool>', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def tools_update(tool):
		"""(Controller) Update an existing tool from HTML form POST"""
		tid = (tool)
		r = Tool.query.filter(Tool.id==tid).one_or_none()
		if not r:
                    flash("Error: Tool not found")
                    return redirect(url_for('tools.tools'))
		r.name = (request.form['input_name'])
		r.short = (request.form['input_short'])

		# None handling shouldn't beneeded with new global form template
		if (request.form['input_node_id'] == "None"):
			r.node_id = None
		else:
			r.node_id = (request.form['input_node_id'])
		r.resource_id = (request.form['input_resource_id'])
		db.session.commit()
		flash("Tool updated")
		return redirect(url_for('tools.tools'))

@blueprint.route('/<string:tool>/delete', methods=['POST'])
@roles_required(['Admin','RATT'])
def tool_delete(tool):
		"""(Controller) Delete a tool. Shocking."""
                r = Tool.query.filter(Tool.id == tool).one()
                db.session.delete(r)
                db.session.commit()
		flash("Tool deleted.")
		return redirect(url_for('tools.tools'))

@blueprint.route('/<string:tool>/list', methods=['GET'])
def tool_showusers(tool):
		"""(Controller) Display users who are authorized to use this tool"""
		tid = (tool)
		authusers = db.session.query(AccessByMember.id,AccessByMember.member_id,Member.member)
		authusers = authusers.outerjoin(Member,AccessByMember.member_id == Member.id)
		authusers = authusers.filter(AccessByMember.tool_id == db.session.query(Tool.id).filter(Tool.name == rid))
		authusers = authusers.all()
		return render_template('tool_users.html',rec=rid,users=authusers)

#TODO: Create safestring converter to replace string; converter?
@blueprint.route('/<string:tool>/log', methods=['GET','POST'])
@roles_required(['Admin','RATT'])
def logging(tool):
	 """Endpoint for a tool to log via API"""
	 # TODO - verify tools against global list
	 if request.method == 'POST':
		# YYYY-MM-DD HH:MM:SS
		# TODO: Filter this for safety
		logdatetime = request.form['logdatetime']
		level = safestr(request.form['level'])
		# 'system' for tool system, rfid for access messages
		userid = safestr(request.form['userid'])
		msg = safestr(request.form['msg'])
		sqlstr = "INSERT into logs (logdatetime,tool,level,userid,msg) VALUES ('%s','%s','%s','%s','%s')" % (logdatetime,tool,level,userid,msg)
		execute_db(sqlstr)
		get_db().commit()
		return render_template('logged.html')
	 else:
		if current_user.is_authenticated:
				r = safestr(tool)
				sqlstr = "SELECT logdatetime,tool,level,userid,msg from logs where tool = '%s'" % r
				entries = query_db(sqlstr)
				return render_template('tool_log.html',entries=entries)
		else:
				abort(401)


def _get_tools():
	q = db.session.query(Tool.name,Tool.id)
	q = q.add_column(Resource.name.label("resource_name")).join(Resource,Resource.id==Tool.resource_id)
	q = q.add_column(Node.name.label("node")).outerjoin(Node,Node.id == Tool.node_id)
	#print "QUERY",q
	return q.all()

def register_pages(app):
	app.register_blueprint(blueprint)
