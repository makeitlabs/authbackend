#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs.comments import comments
from authlibs import accesslib
import datetime
from ..google_admin import calendar_read,calendar_create,get_booking,edit_booking, delete_booking
import dateutil.tz

def parse_time_input(tstr):
    if tstr.endswith('Z'):
        return datetime.datetime.fromisoformat(tstr.replace('Z', '+00:00'))
    elif '+' in tstr[-6:] or ('-' in tstr[-6:] and 'T' in tstr):
        return datetime.datetime.fromisoformat(tstr)
    else:
        dt = datetime.datetime.fromisoformat(tstr)
        eastern = dateutil.tz.gettz('US/Eastern')
        return dt.replace(tzinfo=eastern)

blueprint = Blueprint("calendars", __name__, template_folder='templates', static_folder="static",url_prefix="/calendars")

"""

EPILOG_ID	makeitlabs.com_3133373236393938363631@resource.calendar.google.com
MOPA_ID	c_1886b6dkec306jdkk38lsbpbejeo8@resource.calendar.google.com
SHOPBOT_ID	c_188ajec7o5sd8hnglghkkj80c1jh0@resource.calendar.google.com
PROTOTRAK_ID	c_1889s1vmc5pomj84ltqr9eibcfa2k@resource.calendar.google.com
JETLATHE_ID	c_18810t9nfo22qhp9h4fm2ngv5flt0@resource.calendar.google.com
BRIDGEPORT_ID	c_188b54f39t68kgvikia14o9faugs8@resource.calendar.google.com
TORMACH_ID	c_18856dus4un86j67m559qpd1he66c@resource.calendar.google.com
AUTOLIFT    makeitlabs.com_188edv0v5b658jk8h92eemdsdeqom@resource.calendar.google.com
WATERJET    c_188f9bh42ku8ahn2lnqukpc25elbs@resource.calendar.google.com

MACHINESHOP	makeitlabs.com_2d3432333535363639363338@resource.calendar.google.com
AV	c_1885imaecf8ekjg8ida0uaulgg2ku@resource.calendar.google.com
ART	makeitlabs.com_3438353135363139313031@resource.calendar.google.com
CLASSROOM	makeitlabs.com_1885ovbr2ecl0irsh4dq4rc0t5pfa6gb74sjedpo6ksj6d1k64@resource.calendar.google.com
DARKROOM	c_188fr2u7d5i7kgpflmt7ue7rfgo0q@resource.calendar.google.com
EVENT_ROOM	makeitlabs.com_188aq2sk57k2ujq7grms0tavvo1nk@resource.calendar.google.com
CONFERENCE	makeitlabs.com_188634rlsva2kha1iikp7lifrnipo6gb74ojge9g64q3ad1k60@resource.calendar.google.com
EMBROIDERY  c_18896vricr9p2g69hphhra6uhs3r2@resource.calendar.google.com

KERN c_1886igtlroq94ic5hro66r88vg274@resource.calendar.google.com
UV c_18876mnepfo42jnunrjppi4cuqkcu@resource.calendar.google.com

"""

# Add user names to bookings
def add_users(bookings):
    cache = {}
    for b in bookings:
        if b['organizer_email'] in cache:
            b['user'] = cache[b['organizer_email']]
        else:
            x = Member.query.filter(Member.email == b['organizer_email']).one_or_none()
            if x is not None:
                b['user'] = x.member.replace("."," ")
                cache[b['organizer_email']] = b['user']


resources = {
        "av":{
                "url":"av",
                "name":"A/V Studio",
                "img" : "icon_av.png",
                "cal" : "c_1885imaecf8ekjg8ida0uaulgg2ku@resource.calendar.google.com"
                },
        "shopbot":{
                "url":"shopbot",
                "name":"Shopbot",
                "img" : "icon_shopbot.png",
                "cal" : "c_188ajec7o5sd8hnglghkkj80c1jh0@resource.calendar.google.com"
                },
        "darkroom":{
                "url":"darkroom",
                "name":"Darkroom",
                "img" : "icon_darkroom.png",
                "cal" : "c_188fr2u7d5i7kgpflmt7ue7rfgo0q@resource.calendar.google.com"
                },
        "conference":{
                "url":"conference",
                "name":"Conference Room",
                "img" : "icon_conference.png",
                "cal" : "makeitlabs.com_188634rlsva2kha1iikp7lifrnipo6gb74ojge9g64q3ad1k60@resource.calendar.google.com"
                },
        "bridgeport":{
                "url":"bridgeport",
                "name":"Bridgeport Mill",
                "img" : "icon_bridgeport.png",
                "cal" : "c_188b54f39t68kgvikia14o9faugs8@resource.calendar.google.com"
                },
        "tormach":{
                "url":"tormach",
                "name":"Tormach",
                "img" : "icon_tormach.png",
                "cal" : "c_18856dus4un86j67m559qpd1he66c@resource.calendar.google.com"
                },
        "protolathe":{
                "url":"protolathe",
                "name":"Prototrak Lathe",
                "img" : "icon_lathe.png",
                "cal" : "c_1889s1vmc5pomj84ltqr9eibcfa2k@resource.calendar.google.com"
                },
        "event":{
                "url":"event",
                "name":"Event Room",
                "img" : "icon_event.png",
                "cal" : "makeitlabs.com_188aq2sk57k2ujq7grms0tavvo1nk@resource.calendar.google.com"
                },
        "epilog":{
                "url":"Epilog",
                "name":"Epilog Laser",
                "img" : "icon_epilog.png",
                "cal" : "makeitlabs.com_3133373236393938363631@resource.calendar.google.com"
                },
        "mopa":{
                "url":"MOPA",
                "name":"MOPA Laser",
                "img" : "icon_MOPA.png",
                "cal" : "c_1886b6dkec306jdkk38lsbpbejeo8@resource.calendar.google.com"
                },
        "uv":{
                "url":"uv",
                "name":"xTool UV Laser",
                "img" : "icon_uv.png",
                "cal" : "c_18876mnepfo42jnunrjppi4cuqkcu@resource.calendar.google.com"
                },
        "kern":{
                "url":"kern",
                "name":"Kern Laser",
                "img" : "icon_kern.png",
                "cal" : "c_1886igtlroq94ic5hro66r88vg274@resource.calendar.google.com"
                },
        "embroidery":{
                "url":"Embroidery",
                "name":"Embroidery",
                "img" : "icon_embroidery.png",
                "cal":"c_18896vricr9p2g69hphhra6uhs3r2@resource.calendar.google.com"
                },
        "classroom":{
                "url":"Clasroom",
                "name":"Classroom",
                "img" : "icon_classroom.png",
                "cal":"makeitlabs.com_1885ovbr2ecl0irsh4dq4rc0t5pfa6gb74sjedpo6ksj6d1k64@resource.calendar.google.com"
                },
        "auto":{
                "url":"AutoLift",
                "name":"Auto Lift",
                "img" : "icon_auto.png",
                "cal":"makeitlabs.com_188edv0v5b658jk8h92eemdsdeqom@resource.calendar.google.com",
                },
        "waterjet":{
                "url":"Waterjet",
                "name":"Waterjet",
                "img" : "icon_waterjet.png",
                "cal":"c_188f9bh42ku8ahn2lnqukpc25elbs@resource.calendar.google.com"
                },
        "hamshack":{
                "url":"Hamshack",
                "name":"Hamshack",
                "img" : "icon_hamshack.png",
                "cal":"makeitlabs.com_18871j42ru8lgitri015g0rs3c8la@resource.calendar.google.com",
                },
        "fiber":{
                "url":"fiber",
                "name":"Fiber Laser",
                "img" : "icon_fiber.png",
                "cal":"c_188d0nssif766ji6k0jai36vq837g@resource.calendar.google.com"
                },
        }

@blueprint.route('/', methods=['GET'])
@login_required
def calendars():
    return render_template('rescallist.html',resources=resources)

@blueprint.route('/<string:resource>/', methods=['GET'])
@login_required
def resource(resource):
    if resource not in resources:
        flash("Invalid Resource","danger")
        return redirect(url_for('calendars.calendars'))

    entries = calendar_read(current_user.email,resources[resource]['cal'])
    add_users(entries)
    print (entries)
    return render_template('calendar.html',name=resources[resource]['name'],entries=entries,member=current_user.member)


@blueprint.route('/<string:resource>/status/<string:eventid>', methods=['GET'])
@login_required
def status_booking(resource,eventid):
    if resource not in resources:
        flash("Invalid Resource","danger")
        return redirect(url_for('calendars.calendars'))

    status = get_booking(current_user.email,eventid,resources[resource]['cal'])
    return render_template('status.html',name=resources[resource]['name'],status=status)

@blueprint.route('/<string:resource>/delete',methods=['POST'])
@login_required
def delete_event(resource):
    if resource not in resources:
        flash(f"Invalid Resource {resource} ","danger")
        return redirect(url_for('calendars.calendars'))

    debug = f"{request.form}"

    eventid = request.form.get('calendar_id','')
    if eventid == "":
        flash(f"No event id specified","danger")
        return redirect(url_for('calendars.calendars'))
    result = delete_booking(current_user.email,eventid)
    if result:
        flash("ERROR: Please try via Google Calendar","danger")
    else:
        flash("Deleted")
    return redirect(url_for('calendars.calendars'))

@blueprint.route('/<string:resource>/update', methods=['POST'])
@login_required
def update_booking(resource):
    if resource not in resources:
        flash("Invalid Resource","danger")
        return redirect(url_for('calendars.calendars'))

    description = request.form.get('description','')
    eventid = request.form.get('calendar_id','')
    start = parse_time_input(request.form.get('start'))
    end = parse_time_input(request.form.get('end'))

    user_name = f"{current_user.firstname} {current_user.lastname}".strip() if (getattr(current_user, 'firstname', None) and getattr(current_user, 'lastname', None)) else current_user.member.replace(".", " ")

    result = edit_booking(current_user.email,eventid,description,start,end,user_name=user_name)
    if result is not None:
        flash (f"Failed: {result}","danger")
        return redirect(url_for('calendars.calendars'))


    return redirect(url_for('calendars.status_booking',resource=resource,eventid=eventid))

@blueprint.route('/<string:resource>/create', methods=['POST'])
@login_required
def create_booking(resource):
    if resource not in resources:
        flash("Invalid Resource","danger")
        return redirect(url_for('calendars.calendars'))

    debug=f"{request.form}\n"
    description = request.form.get('description','')
    start = parse_time_input(request.form.get('start'))
    end = parse_time_input(request.form.get('end'))

    user_name = f"{current_user.firstname} {current_user.lastname}".strip() if (getattr(current_user, 'firstname', None) and getattr(current_user, 'lastname', None)) else current_user.member.replace(".", " ")

    try:
        event_id,result = calendar_create(current_user.email,resources[resource]['cal'],description,start,end,user_name=user_name)
    except BaseException as e:
        debug += f"\nBaseException {e}\n"
        return render_template('debug.html',debug=debug)

    return redirect(url_for('calendars.status_booking',resource=resource,eventid=event_id))

def register_pages(app):
	app.register_blueprint(blueprint)
