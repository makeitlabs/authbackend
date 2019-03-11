# vim:shiftwidth=2:expandtab


from ..templateCommon import  *
from authlibs.comments import comments

blueprint = Blueprint("nodes", __name__, template_folder='templates', static_folder="static",url_prefix="/nodes")



@blueprint.route('/', methods=['GET'])
@login_required
def nodes():
	"""(Controller) Display Nodes and controls"""
	nodes = _get_nodes()
	access = {}
	resources=Resource.query.all()
	return render_template('nodes.html',nodes=nodes,editable=True,node={},resources=resources)

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def nodes_create():
	"""(Controller) Create a node from an HTML form POST"""
	r = Node()
        r.name = (request.form['input_name'])
        r.mac = (request.form['input_mac'])
	db.session.add(r)
        db.session.commit()
	flash("Created.")
	return redirect(url_for('nodes.nodes'))

@blueprint.route('/<string:node>', methods=['GET'])
@login_required
def nodes_show(node):
	"""(Controller) Display information about a given node"""
	r = Node.query.filter(Node.id==node).one_or_none()
	if not r:
		flash("Node not found")
		return redirect(url_for('nodes.nodes'))
	readonly=False
	if (not current_user.privs('RATT')):
		readonly=True
	resources=Resource.query.all()
	params=[]
	kv = KVopt.query.add_column(NodeConfig.value).add_column(NodeConfig.id).outerjoin(NodeConfig,((KVopt.id == NodeConfig.key_id) & (NodeConfig.node_id == node)))
	kv = kv.order_by(KVopt.keyname)
	kv = kv.order_by(KVopt.displayOrder)
	kv = kv.all()
	for (kv,v,ncid) in kv:
		xp=kv.keyname.split('.')
		if len(xp) ==1:
			gpname=""
			itemname=xp[0]
		else:
			gpname=".".join(xp[0:-1])
			itemname=xp[-1]

		if (len(xp)==2):
			indent=''
		else:
			indent='style=margin-left:{0}px;border-left-color:aliceblue;border-left-width:10px;border-left-style:solid;padding-left:5px'.format((len(xp)-2)*30)

		initialvalue=v
		if not initialvalue:
			initialvalue = kv.default if kv.default else ''

		default = kv.default if kv.default else ''
		if kv.kind == "boolean":
			if default:
				default="true"
			else:
				default="false"
				
		params.append({
				'name':kv.keyname,
				'groupname':gpname,
				'itemname':itemname,
				'default':default,
				'description':kv.description if kv.description else '',
				'options':kv.options.split(";") if kv.options else None,
				'value':v if v else '',
				'initialvalue':initialvalue,
				'kind':kv.kind,
				'id':kv.id,
				'indent':indent,
				'ncid':ncid if ncid else '',
			})

	cc=comments.get_comments(node_id=node)
	return render_template('node_edit.html',node=r,resources=resources,readonly=readonly,params=params,comments=cc)

@blueprint.route('/<string:node>', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def nodes_update(node):
		"""(Controller) Update an existing node from HTML form POST"""
		tid = (node)
		r = Node.query.filter(Node.id==tid).one_or_none()
		if not r:
                    flash("Error: Node not found")
                    return redirect(url_for('nodes.nodes'))
		r.name = (request.form['input_name'])
		r.mac = (request.form['input_mac'])
		for x in request.form:
			if x.startswith("key_orig_"):
				kid=x.split("_")[-1]
				orig=request.form["key_orig_"+kid]
				if "key_input_"+kid in request.form:
					val=request.form["key_input_"+kid]
				else:
					val=""
				ncid=request.form["ncid_"+kid]
				if (val != orig):
					# Change was made
					if val == "":
						d = NodeConfig.query.filter(NodeConfig.id==ncid).one_or_none()
						if d:
							db.session.delete(d)
					elif ncid:
						n = NodeConfig.query.filter(NodeConfig.id==ncid).one_or_none()
						if n:
							n.value=val
						else:
							db.session.add(NodeConfig(node_id=node,value=val,key_id=kid))
					else:
						db.session.add(NodeConfig(node_id=node,value=val,key_id=kid))
		db.session.commit()
		flash("Node updated")
		return redirect(url_for('nodes.nodes'))

@blueprint.route('/<string:node>/delete', methods=['POST'])
@roles_required(['Admin','RATT'])
def node_delete(node):
		"""(Controller) Delete a node. Shocking."""
                r = Node.query.filter(Node.id == node).one()
                db.session.delete(r)
                db.session.commit()
		flash("Node deleted.")
		return redirect(url_for('nodes.nodes'))

@blueprint.route('/<string:node>/list', methods=['GET'])
def node_showusers(node):
		"""(Controller) Display users who are authorized to use this node"""
		tid = (node)
		authusers = db.session.query(AccessByMember.id,AccessByMember.member_id,Member.member)
		authusers = authusers.outerjoin(Member,AccessByMember.member_id == Member.id)
		authusers = authusers.filter(AccessByMember.node_id == db.session.query(Node.id).filter(Node.name == rid))
		authusers = authusers.all()
		return render_template('node_users.html',node=rid,users=authusers)

#TODO: Create safestring converter to replace string; converter?
@blueprint.route('/<string:node>/log', methods=['GET','POST'])
@roles_required(['Admin','RATT'])
def logging(node):
	 """Endpoint for a node to log via API"""
	 # TODO - verify nodes against global list
	 if request.method == 'POST':
		# YYYY-MM-DD HH:MM:SS
		# TODO: Filter this for safety
		logdatetime = request.form['logdatetime']
		level = safestr(request.form['level'])
		# 'system' for node system, rfid for access messages
		userid = safestr(request.form['userid'])
		msg = safestr(request.form['msg'])
		sqlstr = "INSERT into logs (logdatetime,node,level,userid,msg) VALUES ('%s','%s','%s','%s','%s')" % (logdatetime,node,level,userid,msg)
		execute_db(sqlstr)
		get_db().commit()
		return render_template('logged.html')
	 else:
		if current_user.is_authenticated:
				r = safestr(node)
				sqlstr = "SELECT logdatetime,node,level,userid,msg from logs where node = '%s'" % r
				entries = query_db(sqlstr)
				return render_template('node_log.html',entries=entries)
		else:
				abort(401)


def _get_nodes():
	q = db.session.query(Node.name,Node.mac,Node.id)
	# q = q.add_column(Resource.name.label("resource_name")).join(Resource,Resource.id==Node.resource_id)
	return q.all()

def register_pages(app):
	app.register_blueprint(blueprint)
