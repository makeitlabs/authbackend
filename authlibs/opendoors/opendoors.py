#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs.comments import comments
from authlibs import accesslib
import time
import struct
import hmac
import hashlib
import base64
import paho.mqtt.publish as mqtt_pub

blueprint = Blueprint("opendoors", __name__, template_folder='templates', static_folder="static",url_prefix="/opendoors")

def sign_request(base64_secret: str, member: str, tool: str, ts: int):
    """
    Compute HMAC-SHA256 over (member || uint64_be(timestamp)) using a base64-encoded secret.

    Args:
        base64_secret: Base64-encoded shared secret key.
        member: Member identifier string (UTF-8).
        ts: Timestamp as an integer (uint64). Use seconds or milliseconds consistently.

    Returns:
        (signature_hex, signature_base64)
    """
    # 1) Decode the base64 secret into raw bytes
    try:
        secret = base64.b64decode(base64_secret, validate=True)
    except Exception as e:
        raise ValueError(f"Invalid base64 secret: {e}")
    if not secret:
        raise ValueError("Secret cannot be empty")

    # 2) Serialize message: member bytes + timestamp (uint64 big-endian)
    member_bytes = member.encode("utf-8")
    tool_bytes = tool.encode("utf-8")
    ts_bytes = struct.pack(">Q", ts)  # '>Q' = big-endian unsigned long long (uint64)

    msg = member_bytes + tool_bytes + ts_bytes

    # 3) Compute HMAC-SHA256
    mac = hmac.new(secret, msg, hashlib.sha256).digest()

    # 4) Return hex and base64 encodings
    sig_hex = mac.hex()
    sig_b64 = base64.b64encode(mac).decode("ascii")
    return sig_b64

def getRequestNetwork(request):
    fwf = ''
    rip = ''
    if 'X-Forwarded-For' in request.headers: fwf = request.headers['X-Forwarded-For']
    if 'X-Real-Ip' in request.headers: rip = request.headers['X-Real-Ip']
    onLocalWifi  = (fwf.startswith("10.25.") and fwf.startswith("10.25."))
    noProxy = (fwf == '' or rip == '')
    return (onLocalWifi,noProxy)

@blueprint.route('/', methods=['GET'])
@login_required
def opendoors():
    """(Controller) Display Tools and controls"""
    disable=True
    show_swipe_unlock=False
    onLocalWifi, noProxy  = getRequestNetwork(request)
    if current_user.has_roles('Admin'):
        if noProxy:
            banner = '<p>Admin seems to not be using proxy</p>'
            disable=False
        elif onLocalWifi:
            banner = '<p>Admin user is on Wi-Fi</p>'
            disable=False
        else:
            banner = f'<p><b>WARNING:</b> Admin user is <b>not</b> on Member Wi-Fi network. Swipe to unlock remote door controls.</p>'
            disable=True
            show_swipe_unlock=True

    else:
        if noProxy:
            banner = '<p>Network Error: Internal proxy not detectd</p>'
        elif onLocalWifi:
            banner = '<p></p>'
            disable=False
        else:
            banner = '<p>You must be in the lab and on the local Member Wi-Fi Network to opern remote doors. Please wait or make sure you are connected</p>'

    tools = _get_opendoors()



    return render_template('opendoors.html',tools=tools,banner=banner,disable=disable,show_swipe_unlock=show_swipe_unlock)


@blueprint.route('/<string:tool>', methods=['GET'])
@login_required
def open(tool):
    """(Controller) Display information about a given opendoor"""
    r = Tool.query.filter(Tool.id==tool)
    r = r.outerjoin(Node,Node.id == Tool.node_id)
    r = r.join(AccessByMember,
    and_(
        AccessByMember.resource_id == Tool.resource_id,
        AccessByMember.member_id == current_user.id
    )
)
    r = r.add_columns(Node.mac,AccessByMember)
    r = r.one_or_none()
    if not r:
        flash("Tool not found")
        return redirect(url_for('opendoors.opendoors'))

    onLocalWifi, noProxy  = getRequestNetwork(request)
    if not current_user.has_roles('Admin'):
        banner = '<p>You <b>must</b> be on the Member Wi-Fi Network to open a door</p>'
        if noProxy:
            flash("Network Error No Proxy","danger")
            return redirect(url_for('opendoors.opendoors'))
        if not onLocalWifi:
            flash("Must be on member network Wi-Fi","danger")
            return redirect(url_for('opendoors.opendoors'))

    privs = accesslib.user_privs_on_resource(member=current_user,resource=r[0])
    readonly=False
    if privs < AccessByMember.LEVEL_USER:
        flash("You don't have access to this door")
        return redirect(url_for('index'))

    acc = accesslib.access_query(r[0].resource_id,current_user.id,tags=False)
    acc = acc.first()
    if  not acc:
        flash("You don't have access to this door")
        return redirect(url_for('index'))

    if not current_app.config['globalConfig'].Config.has_option('General','OpendoorSharedSecret'):
        flash("Internal error: Not credentialed","danger")
        return redirect(url_for('index'))
    base64_secret = current_app.config['globalConfig'].Config.get('General','OpendoorSharedSecret')
    ts_seconds = int(time.time())
    sig_b64 = sign_request(base64_secret,  current_user.member, r[0].name, ts_seconds)
    j = json.dumps ({
        "member":current_user.member,
        "timestamp" : ts_seconds,
        "tool" : r[0].name,
        "signature" : sig_b64
        })
    gc= current_app.config['globalConfig']
    topic=  f"ratt/control/node/{r[1]}/open"
    debug = ""
    if current_user.has_roles('Admin'):
        # Just some debug
        debug = f"Send: {j}\nTo: {topic}\n"
    try:
        mqtt_pub.single(topic, j, hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
        result = "Door Open Initiated"
    except BaseException as e:
        result = "Door Open Failed"
        debug += f"\nError: {e}"
    return render_template('result.html',result=result,debug=debug)



def _get_opendoors():
    q = db.session.query(Tool.name, Tool.id, Tool.resource_id).filter(Tool.remotable == 1)
    q = q.add_column(Resource.name.label("resource_name")).join(Resource, Resource.id == Tool.resource_id)
    q = q.add_column(Node.name.label("node")).outerjoin(Node, Node.id == Tool.node_id)
    # Filter to only doors the current user has access to
    q = q.join(AccessByMember, and_(
        AccessByMember.resource_id == Tool.resource_id,
        AccessByMember.member_id == current_user.id
    ))
    # Check subscription/membership status using access_query
    results = []
    for tool in q.all():
        # tool[2] is resource_id
        acc = accesslib.access_query(tool[2], current_user.id, tags=False).first()
        if acc:
            u = accesslib.accessQueryToDict(acc)
            (warning, allowed) = accesslib.determineAccess(u, None)
            print (f"Tool: {tool} is {tool[0]} {tool[1]}")
            if allowed != 'false':
                # Return tuple without resource_id (name, id, resource_name, node)
                #results.append((tool[0], tool[1], tool[3], tool[4]))
                results.append({
                    'name':tool[0],
                    'id':tool[1],
                    })

    return results

def register_pages(app):
	app.register_blueprint(blueprint)
