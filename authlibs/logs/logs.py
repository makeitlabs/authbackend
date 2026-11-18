# vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from datetime import datetime, timedelta
from .. import accesslib
from .. import ago
import csv
import io
import subprocess
import glob
from urllib.parse import urlencode

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("logs", __name__, template_folder='templates', static_folder="static",url_prefix="/logs")

# --------------------------------------
# Routes
#  /test : Show (HTTP GET - members()), Create new (HTTP POST - member_add())
#  /test/<id> - Some ID
# --------------------------------------

# ------------------------------------------------------------
# Logs  
#
# Things log like crazy. Therefore logs are designed to
# be cheap to write, and to be compartimentalizable so
# that they don't interfere with other stuff.
#
# So we put logs in a separate databse. Maybe someday this
# could be a completely different type of datastore.
#
# Because of this, we can't do relational queries between
# the log and main databases. 
#
# Because of all this, logs are expensive to read. This might
# not be too bad because we don't read them all that often.
# ------------------------------------------------------------

CSV_MAX_ROWS = 25000


def _build_logs_url(**overrides):
    """Build a logs URL preserving current query args with optional overrides (None removes a key)."""
    params = request.args.to_dict(flat=False)
    for k, v in overrides.items():
        if v is None:
            params.pop(k, None)
        else:
            params[k] = [str(v)]
    qs = urlencode(params, doseq=True)
    base = url_for('logs.logs')
    return f"{base}?{qs}" if qs else base


@blueprint.route('/', methods=['GET'])
@login_required
def logs():
    eastern = dateutil.tz.gettz('US/Eastern')
    utc = dateutil.tz.gettz('UTC')
    now = datetime.now()
    limit = 200
    offset = 0
    format = request.values.get('format', 'html')
    evt = eventtypes.get_events()
    event_categories = eventtypes.get_event_categories()
    category_map = eventtypes.get_category_map()

    # Query main DB to Build relational tables
    tools = {t.id: t.name for t in Tool.query.all()}
    resources = {r.id: r.name for r in Resource.query.all()}
    nodes = {n.id: n.name for n in Node.query.all()}
    members = {}
    for m in Member.query.all():
        members[m.id] = {
            'member': m.member,
            'first': m.firstname,
            'last': m.lastname,
            'email': m.email
        }

    # Parse user-supplied filters once
    selected_resources = []
    selected_members = []
    selected_tools = []
    selected_nodes = []
    selected_categories = []
    selected_events = []

    for x in request.values:
        if x.startswith("input_resource_"):
            val = x.replace("input_resource_", "")
            if val.isdigit():
                selected_resources.append(int(val))
        elif x.startswith("input_member_"):
            val = x.replace("input_member_", "")
            if val.isdigit():
                selected_members.append(int(val))
        elif x.startswith("input_tool_"):
            val = x.replace("input_tool_", "")
            if val.isdigit():
                selected_tools.append(int(val))
        elif x.startswith("input_node_"):
            val = x.replace("input_node_", "")
            if val.isdigit():
                selected_nodes.append(int(val))
        elif x.startswith("input_category_"):
            cat_key = x.replace("input_category_", "")
            if cat_key in category_map:
                selected_categories.append(cat_key)
        elif x.startswith("input_event_"):
            val = x.replace("input_event_", "")
            if val.isdigit():
                selected_events.append(int(val))

    date_start_str = request.values.get('input_date_start', '').strip()
    date_end_str = request.values.get('input_date_end', '').strip()

    # Build base query
    q = db.session.query(Logs).order_by(Logs.time_reported.desc())
    has_user_filter = False

    if selected_resources:
        q = q.filter(Logs.resource_id.in_(selected_resources))
        has_user_filter = True

    if selected_members:
        q = q.filter(Logs.member_id.in_(selected_members))
        has_user_filter = True

    if selected_tools:
        q = q.filter(Logs.tool_id.in_(selected_tools))
        has_user_filter = True

    if selected_nodes:
        q = q.filter(Logs.node_id.in_(selected_nodes))
        has_user_filter = True

    if date_start_str:
        try:
            dt = datetime.strptime(date_start_str, "%m/%d/%Y")
            q = q.filter(Logs.time_reported >= dt)
            has_user_filter = True
        except ValueError:
            flash("Invalid start date format (expected MM/DD/YYYY)", "warning")

    if date_end_str:
        try:
            dt = datetime.strptime(date_end_str, "%m/%d/%Y") + timedelta(days=1)
            q = q.filter(Logs.time_reported < dt)
            has_user_filter = True
        except ValueError:
            flash("Invalid end date format (expected MM/DD/YYYY)", "warning")

    # Access-control filters based on current user's privileges
    if current_user.privs('Useredit', 'Finance', 'RATT'):
        pass
    elif accesslib.user_is_authorizor(current_user, level=AccessByMember.LEVEL_ARM):
        myres = AccessByMember.query.join(
            Resource,
            ((Resource.id == AccessByMember.resource_id) & (AccessByMember.level >= AccessByMember.LEVEL_ARM))
        )
        myres = myres.filter(AccessByMember.member_id == current_user.id)
        myres = myres.add_columns(Resource.id, Resource.name).all()
        my_resources = [x.id for x in myres]

        my_tools = []
        ndlist = {}
        for t in Tool.query.filter(Tool.resource_id.in_(my_resources)).all():
            my_tools.append(t.id)
            ndlist[t.node_id] = 1
        my_nodes = list(ndlist.keys())

        my_filter = and_(
            Logs.member_id.__eq__(current_user.id),
            Logs.event_type.__ne__(eventtypes.RATTBE_LOGEVENT_COMMENT.id)
        )
        filter_group = (
            Logs.node_id.in_(my_nodes),
            Logs.resource_id.in_(my_resources),
            Logs.tool_id.in_(my_tools),
            my_filter
        )
        q = q.filter(or_(*filter_group))
    else:
        q = q.filter(Logs.member_id == current_user.id)
        q = q.filter(Logs.event_type != eventtypes.RATTBE_LOGEVENT_COMMENT.id)

    # Legacy / direct query-param filters
    if 'member' in request.values:
        q = q.filter((Logs.member_id == members[request.values['member']]) | (Logs.doneby == members[request.values['member']]))
        has_user_filter = True
    if 'memberid' in request.values:
        q = q.filter((Logs.member_id == request.values['memberid']) | (Logs.doneby == request.values['memberid']))
        has_user_filter = True
    if 'resource' in request.values:
        q = q.filter(Logs.resource_id == resources[request.values['resource']])
        has_user_filter = True
    if 'resourceid' in request.values:
        q = q.filter(Logs.resource_id == request.values['resourceid'])
        has_user_filter = True
    if 'tool' in request.values:
        q = q.filter(Logs.tool_id == tools[request.values['tool']])
        has_user_filter = True
    if 'toolid' in request.values:
        q = q.filter(Logs.tool_id == request.values['toolid'])
        has_user_filter = True
    if 'before' in request.values:
        q = q.filter(Logs.time_reported <= request.values['before'])
        has_user_filter = True
    if 'after' in request.values:
        q = q.filter(Logs.time_reported >= request.values['after'])
        has_user_filter = True

    # Event category & specific event filters
    filtered_event_ids = set(selected_events)
    for cat_key in selected_categories:
        filtered_event_ids.update(category_map[cat_key]['events'])

    if filtered_event_ids:
        q = q.filter(Logs.event_type.in_(filtered_event_ids))
        has_user_filter = True
    else:
        # Default behavior when no explicit category/event filter is active:
        # hide noisy tool active/inactive heartbeats unless 'activity' is checked
        if 'activity' not in request.values:
            q = q.filter(Logs.event_type != eventtypes.RATTBE_LOGEVENT_TOOL_ACTIVE.id)
            q = q.filter(Logs.event_type != eventtypes.RATTBE_LOGEVENT_TOOL_INACTIVE.id)

    if 'hidetoolusage' in request.values:
        q = q.filter(Logs.event_type != eventtypes.RATTBE_LOGEVENT_TOOL_POWEROFF.id)
        q = q.filter(Logs.event_type != eventtypes.RATTBE_LOGEVENT_TOOL_POWERON.id)
        q = q.filter(Logs.event_type != eventtypes.RATTBE_LOGEVENT_TOOL_LOGIN.id)
        q = q.filter(Logs.event_type != eventtypes.RATTBE_LOGEVENT_TOOL_LOGOUT.id)
        q = q.filter(Logs.event_type != eventtypes.RATTBE_LOGEVENT_TOOL_LOGIN_COMBO.id)
        q = q.filter(Logs.event_type != eventtypes.RATTBE_LOGEVENT_TOOL_PROHIBITED.id)
        q = q.filter(Logs.event_type != eventtypes.RATTBE_LOGEVENT_TOOL_COMBO_FAILED.id)

    # Guardrails for CSV export: require at least one filter and enforce row cap
    if format == "csv":
        if not has_user_filter:
            flash("Please apply at least one filter (e.g. a date range, member, resource, tool, node, or event type) before exporting to CSV.", "warning")
            return redirect(_build_logs_url(format=None))
        csv_check_count = q.limit(CSV_MAX_ROWS + 1).count()
        if csv_check_count > CSV_MAX_ROWS:
            flash(f"CSV export is limited to {CSV_MAX_ROWS:,} rows (your filter matched more than {CSV_MAX_ROWS:,}). Please narrow your date range or filters.", "danger")
            return redirect(_build_logs_url(format=None))
        dbq = q
        count = 0
    elif format == "html":
        if 'offset' in request.values:
            offset = int(request.values['offset'])
        if 'limit' in request.values:
            if request.values['limit'] != "all":
                limit = int(request.values['limit'])
            else:
                limit = 200
        count = q.count()
        dbq = q
        if limit > 0:
            dbq = dbq.limit(limit)
        if offset > 0:
            dbq = dbq.offset(offset)
    else:
        flash("Invalid format requested", "danger")
        return redirect(_build_logs_url(format=None))

    def generate(fmt=None):
        fields = ['datetime', 'user', 'member_id', 'email', 'tool', 'node', 'resource', 'event', 'doneby', 'message']
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(fields)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

        row_iter = dbq.yield_per(1000) if fmt == "csv" else dbq.all()
        for l in row_iter:
            r = {}
            r['datetime'] = l.time_logged.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)

            if fmt != "csv":
                r['date_str'] = r['datetime'].strftime('%Y-%m-%d')
                r['is_today'] = (r['datetime'].date() == now.date())
                (r['when'], r['ago'], r['othertime']) = ago.ago(r['datetime'], now)

            if not l.member_id:
                r['member_id'] = ""
                r['user'] = ""
                r['email'] = ""
            elif l.member_id in members:
                r['user'] = ""
                if members[l.member_id]['last']:
                    r['user'] = members[l.member_id]['last']
                if members[l.member_id]['last']:
                    r['user'] += ", " + members[l.member_id]['first']
                if r['user'] == "":
                    r['user'] = members[l.member_id]['member']
                r['email'] = members[l.member_id]['email']
                r['member_id'] = members[l.member_id]['member']
            else:
                r['user'] = "Member #" + str(l.member_id)
                r['member_id'] = str(l.member_id)
                r['email'] = ""

            r['tool_id'] = l.tool_id
            if not l.tool_id:
                r['tool'] = ""
            elif l.tool_id in tools:
                r['tool'] = tools[l.tool_id]
            else:
                r['tool'] = "Tool #" + str(l.tool_id)

            r['node_id'] = l.node_id
            if not l.node_id:
                r['node'] = ""
            elif l.node_id in nodes:
                r['node'] = nodes[l.node_id]
            else:
                r['node'] = "Node #" + str(l.node_id)

            if not l.resource_id:
                r['resource'] = ""
            elif l.resource_id in resources:
                r['resource'] = resources[l.resource_id]
            else:
                r['resource'] = "Resource #" + str(l.resource_id)

            if l.event_type in evt:
                r['event'] = evt[l.event_type]
            else:
                r['event'] = l.event_type

            if l.message:
                if l.message.startswith("kioskimages:"):
                    r['message'] = "See Images"
                    if fmt != "csv":
                        r['extern_link'] = url_for("logs.kioskentry", ke=l.message.replace("kioskimages:", ""))
                else:
                    r['message'] = l.message
            else:
                r['message'] = ""

            if not l.doneby:
                r['doneby'] = ""
                r['admin_id'] = ""
            elif l.doneby in members:
                if not members[l.doneby]['last']:
                    r['doneby'] = members[l.doneby]['member']
                else:
                    r['doneby'] = str(members[l.doneby]['last']) + ", " + str(members[l.doneby]['first'])
                r['admin_id'] = members[l.doneby]['member']
            else:
                r['doneby'] = "Member #" + str(l.doneby)

            if fmt == "csv":
                writer.writerow([r.get(f, '') for f in fields])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)
            else:
                yield r

    if format == "csv":
        resp = Response(generate(fmt="csv"), mimetype='text/csv')
        resp.headers['Content-Disposition'] = 'attachment; filename=log.csv'
        return resp

    log_rows = generate(fmt="html")

    nextoffset = offset + limit
    if offset >= count - limit:
        nexturl = None
    else:
        nexturl = _build_logs_url(offset=nextoffset)

    prevoffset = max(0, offset - limit)
    if offset <= 0:
        prevurl = None
    else:
        prevurl = _build_logs_url(offset=prevoffset)

    firsturl = _build_logs_url(offset=None)
    lo = min(offset + limit, count)
    lastoffset = max(0, count - limit)
    lasturl = _build_logs_url(offset=lastoffset)
    csvurl = _build_logs_url(format='csv', offset=None, limit=None)

    meta = {
        'offset': offset,
        'limit': limit,
        'first': firsturl,
        'prev': prevurl,
        'next': nexturl,
        'last': lasturl,
        'count': count,
        'csvurl': csvurl,
        'displayoffset': offset + 1 if count > 0 else 0,
        'lastoffset': lo,
        'today_str': now.strftime('%Y-%m-%d')
    }
    if current_user.privs('Useredit', 'Finance', 'RATT'):
        meta['nomembersearch'] = True
    else:
        meta['nomembersearch'] = False

    fil_resources = Resource.query.order_by(Resource.name).all()
    fil_tools = Tool.query.order_by(Tool.name).all()
    fil_nodes = Node.query.order_by(Node.name).all()
    sorted_events = sorted(evt.items(), key=lambda item: item[1].lower())

    active_member_objs = [
        {'id': mid, 'label': members[mid]['member']}
        for mid in selected_members if mid in members
    ]
    active_filters = {
        'resources': set(selected_resources),
        'tools': set(selected_tools),
        'nodes': set(selected_nodes),
        'categories': set(selected_categories),
        'events': set(selected_events),
        'members': active_member_objs,
        'date_start': date_start_str,
        'date_end': date_end_str,
        'activity': 'activity' in request.values,
        'hidetoolusage': 'hidetoolusage' in request.values,
        'has_any': has_user_filter or ('activity' in request.values) or ('hidetoolusage' in request.values),
        'resource_names': [resources[rid] for rid in selected_resources if rid in resources],
        'tool_names': [tools[tid] for tid in selected_tools if tid in tools],
        'node_names': [nodes[nid] for nid in selected_nodes if nid in nodes],
        'category_labels': [category_map[k]['label'] for k in selected_categories if k in category_map],
        'event_names': [evt[eid] for eid in selected_events if eid in evt],
    }

    return render_template(
        'logs.html',
        logs=log_rows,
        resources=fil_resources,
        tools=fil_tools,
        nodes=fil_nodes,
        event_categories=event_categories,
        all_events=sorted_events,
        active_filters=active_filters,
        meta=meta
    )


@blueprint.route('/kiosk/<string:ke>')
def kioskentry(ke):
  ke = ke.replace("/","")
  ke = ke.replace(".","")
  imagecode=ke
  ke = ke.replace("kioskimages:","")
  if not current_user.is_arm() and (len(current_user.effective_roles()) == 0):
    flash("Not authorized for this page","warning")
    return redirect(url_for("index"))
  try:
    obj=json.load(open("authlibs/logs/static/kioskimages/"+imagecode+".json"))
    txt=obj['txt']
    res=obj['res']
  except:
    obj=None
    txt=""
    res=0
  if obj is None:
    try:
      cam_slackchan = current_app.config['globalConfig'].Config.get('cameras','slackchan')
      s = subprocess.Popen(['/var/www/covosk-cv/covid-mask-detector/testone.py',imagecode],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
      txt = s.stdout.read().strip()
      stderr = s.stderr.read().strip()
      if stderr and stderr != "":
          txt += "\nSTDERR: "+stderr
      res = s.wait()
      json.dump({'txt':txt,'res':res},open("authlibs/logs/static/kioskimages/"+imagecode+".json","w"))
    except BaseException as e:
      logger.error("Kiosk mask check error {0}".format(e))
      txt="BaseException:"+str(e)
  return render_template('kiosk_entry.html',entry=ke,txt=txt,res=res)
  
blueprint.route('/large.csv')
def generate_large_csv():
    def generate():
        for row in iter_all_rows():
            yield ','.join(row) + '\n'
    return Response(generate(), mimetype='text/csv')

@blueprint.route('/train/<string:ke>')
def kiosktrain(ke):
  ke = ke.replace("/","")
  ke = ke.replace(".","")
  imagecode=ke
  data={}
  try:
    data = json.load(open("authlibs/logs/static/kioskimages/{0}.irtrain".format(ke)))
  except:
    pass
  #print ("LOADED DATA",data)
  if 'save_good' in request.values:
    data['goodStartX'] = int(request.values['startX'])
    data['goodStartY'] = int(request.values['startY'])
    data['goodEndX'] = int(request.values['endX'])
    data['goodEndY'] = int(request.values['endY'])
    json.dump(data,open("authlibs/logs/static/kioskimages/{0}.irtrain".format(ke),"w"))
    return redirect(url_for("logs.kiosktrain",ke=ke))
  if 'save_bad' in request.values:
    data['badStartX'] = int(request.values['startX'])
    data['badStartY'] = int(request.values['startY'])
    data['badEndX'] = int(request.values['endX'])
    data['badEndY'] = int(request.values['endY'])
    json.dump(data,open("authlibs/logs/static/kioskimages/{0}.irtrain".format(ke),"w"))
    return redirect(url_for("logs.kiosktrain",ke=ke))
  if 'mark_invalid' in request.values:
    json.dump({},open("authlibs/logs/static/kioskimages/{0}.irtrain".format(ke),"w"))
    return redirect(url_for("logs.kiosktrain",ke=ke))
  g = glob.glob("authlibs/logs/static/kioskimages/*_ir.jpg")
  res=""
  if ke == "0000":
    ke = g[0].split("/")[-1].replace("_ir.jpg","")
  n=""
  p=""
  found_index="??"
  for (i,x) in enumerate(g):
    #print "COMPARE",x,ke
    if x == "authlibs/logs/static/kioskimages/{0}_ir.jpg".format(ke):
      #print ("FOUND")
      found_index=i
      try:
        p = g[i-1].split("/")[-1].replace("_ir.jpg","")
      except:
        pass
      try:
        n = g[i+1].split("/")[-1].replace("_ir.jpg","")
      except:
        pass
  txt = "Index "+str(found_index)+"\r\n"
  txt += ke
  drawcode=""
  if 'goodStartX' in data:
    drawcode += "dorect({0},{1},{2},{3},\"#ffffff80\");".format(
      data['goodStartX'],
      data['goodStartY'],
      data['goodEndX'],
      data['goodEndY'])
  if 'badStartX' in data:
    drawcode += "dorect({0},{1},{2},{3},\"#00000080\");".format(
      data['badStartX'],
      data['badStartY'],
      data['badEndX'],
      data['badEndY'])
  #txt +="\r\n"+str(g)
  #txt +="\r\n"+str(g)
  return render_template('kiosk_train.html',p=p,n=n,entry=ke,txt=txt,res=res,drawcode=drawcode)

def register_pages(app):
        app.register_blueprint(blueprint)
