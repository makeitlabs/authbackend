# vim:shiftwidth=2


from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago
import stripe
import redis
import json
import datetime
from authlibs.slackutils import send_slack_message
from flask import make_response
import paho.mqtt.publish as mqtt_pub

blueprint = Blueprint("facility", __name__, template_folder='templates', static_folder="static",url_prefix="/facility")


temperatures=[50,55,60,65,68,70,72,74,76,80,85]

# Take a temperature, make sure it best-fits into one of the "temperature" buckets

def round_to_closest(number, value1, value2):
    if abs(number - value1) < abs(number - value2):
        return value1
    else:
        return value2

def normalize_temp(temp):
        return (temp)
        if (temp < temperatures[0]):
            return temperatures[0]
        if (temp > temperatures[-1]):
            return temperatures[-1]

        for (h,l) in [(temperatures[i],temperatures[i+1]) for (i,z) in enumerate(temperatures[0:-1])]: 
            if ((temp >= h) and (temp < l)):
                return round_to_closest(temp,l,h)
        return 0

@blueprint.route('/graphs/<string:minisplit>/<string:data>', methods=['GET'])
@login_required
def graphs(minisplit,data):
    return render_template('graphs.html',minisplit=minisplit,data=data)

@blueprint.route('/tempgraph/<string:minisplit>/<string:data>', methods=['GET'])
@login_required
def tempgraph(minisplit,data):
    ysize=300
    xsize=700
    maxtemp=90
    mintemp=20

    xoffset = 50
    yoffset = 50
    maxtime_small = (90*60)
    maxtime_big = (14*24*60*60)
    maxtime_day = (24*60*60)
    now = datetime.datetime.utcnow()
    utcdelta = now - datetime.datetime.now()
    if data == "hours":
        maxtime = maxtime_big
    elif data == "day":
        maxtime = maxtime_day
        data = "hours"
    else:
        maxtime = maxtime_small
    r = redis.Redis()
    x = r.get(f"minisplit_{data}/{minisplit}")
    j = json.loads(x, object_hook=custom_decoder)
    #print ("M")
    circles=[]
    points=[]

    ii = 0
    for i in sorted(j,key = lambda x:x['time']):
        ii += 1
        #print (i)
        rt = i['roomTemp']
        td = (now - i['time']).total_seconds()
        x = (700 * td) / (maxtime)

        if (x>0) and (x < 700):
            #print (rt, td,"xcoord=",700-x,"=",scale_temperature_to_pixel(rt,mintemp,maxtemp,0,ysize))
            y=scale_temperature_to_pixel(rt,mintemp,maxtemp,0,ysize)
            x = (700-x)+xoffset
            points.append(f"{x} {y+yoffset}")
            green = 255-int(i['operating']*255)
            red = int(i['operating']*255)
            color = f"{red:02x}{green:02x}00"
            circles.append(
                    f'<circle style="fill:#{color};fill-rule:evenodd;stroke:none;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:8, 8;stroke-opacity:1" id="circle{ii}" cx="{x}" cy="{y+yoffset}" r="4"> <title>\
                            Temp={int(rt)} Setpoint={int(i["setpoint"])} Running {int(i["operating"]*100)}% at {datetime.datetime.strftime(i["time"]-utcdelta,"%a %b-%d %-I:%M %p")}</title> /> </circle>'

                    )

    #print ()
    expanded = "M " + " ".join(points)
    #print (f'<path style="fill:none;fill-rule:evenodd;stroke:#000000;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;" id="BKGpath" d="{expanded}" />')
    custom = f'<path style="fill:none;fill-rule:evenodd;stroke:#000000;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;" id="BKGpath" d="{expanded}" />'

    for x in circles:
        custom += x

    # time labels
    label=[]
    for i in range(5):
        ago = (maxtime/5)*i
        if (ago < (60*60*18)):
            label.append(datetime.datetime.strftime(datetime.datetime.now() - datetime.timedelta(seconds=ago),"%-I:%M %p"))
        elif (ago < (60*60*24*6)):
            label.append(datetime.datetime.strftime(datetime.datetime.now() - datetime.timedelta(seconds=ago),"%a %-I:%M %p"))
        else:
            label.append(datetime.datetime.strftime(datetime.datetime.now() - datetime.timedelta(seconds=ago),"%a %b-%d"))
    response = make_response(render_template('tempgraph.svg',title=minisplit,custom=custom,label=label))
    response.headers['Content-Type'] = 'image/svg+xml'
    return response


def custom_decoder(obj):
    if 'time' in obj:
        obj['time']= datetime.datetime.fromisoformat(obj['time'])
        #obj['starttime']= obj['time'].replace(minute=0,second=0,microsecond=0)
        #obj['endtime']= obj['time'].replace(minute=59,second=59,microsecond=999999)
    return obj


def scale_temperature_to_pixel(temperature, mintemp, maxtemp, ymin, ymax):
    """
    Scales a temperature value to screen pixel coordinates.

    Args:
        temperature (float): Temperature value to scale.
        mintemp (float): Minimum temperature.
        maxtemp (float): Maximum temperature.
        ymin (int): Minimum y-coordinate (pixel).
        ymax (int): Maximum y-coordinate (pixel).

    Returns:
        int: Scaled y-coordinate (pixel).
    """
    # Normalize temperature to [0, 1] range
    normalized_temp = (temperature - mintemp) / (maxtemp - mintemp)

    # Invert the mapping to handle higher temperatures resulting in lower y-coordinates
    scaled_y = ymax - int(normalized_temp * (ymax - ymin))

    return scaled_y

@blueprint.route('/minisplits', methods=['GET','POST'])
@login_required
def minisplit():
    # First, process POST data if any
    if request.method == "POST" and 'Refresh' in request.form:
        pass
    elif request.method == "POST" and 'override' in request.form:
        try:
          gc= current_app.config['globalConfig']
          topic=  "facility/minisplit/request/"+request.form['override']
          command={'do_override':True}
          message = json.dumps(command)
          mqtt_pub.single(topic, message, hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
          flash("Override Enabled","success")
        except BaseException as e:
            flash("Error updating Minisplit","warning")
            logger.debug("MQTT minisplit failed to publish: "+str(e))
        return redirect(url_for('facility.minisplit'))
    elif request.method == "POST" and 'cancelOverride' in request.form:
        try:
          gc= current_app.config['globalConfig']
          topic=  "facility/minisplit/request/"+request.form['cancelOverride']
          command={'cancel_override':True}
          message = json.dumps(command)
          mqtt_pub.single(topic, message, hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
          flash("Override Canceled","success")
        except BaseException as e:
            flash("Error updating Minisplit","warning")
            logger.debug("MQTT minisplit failed to publish: "+str(e))
        return redirect(url_for('facility.minisplit'))
        return redirect(url_for('facility.minisplit'))

    elif request.method == "POST" and current_user.privs('Facilities'):
        command = {}
        if 'managed' in request.form:
            command['managed'] = request.form['managed']
        if ('managed' not in command) or (command['managed'] == "UNMANAGED"):
            if 'power' in request.form:
                command['power'] = request.form['power'].upper()
            if 'fan' in request.form:
                command['fan'] = request.form['fan'].upper()
            if 'mode' in request.form:
                command['mode'] = request.form['mode'].upper()
            if 'setpoint' in request.form:
                command['setpoint'] = int(request.form['setpoint'])
        if 'managed_setpoint' in request.form:
            command['managed_setpoint'] = int(request.form['managed_setpoint'])
        if 'managed_setpoint_unoccupied' in request.form:
            command['managed_setpoint_unoccupied'] = int(request.form['managed_setpoint_unoccupied'])
        if 'override_setpoint' in request.form:
            command['override_setpoint'] = int(request.form['override_setpoint'])
        if 'override_time' in request.form:
            command['override_time'] = int(request.form['override_time'])
        if 'ir_interval' in request.form:
            command['ir_interval'] = int(request.form['ir_interval'])
        try:
          gc= current_app.config['globalConfig']
          topic=  "facility/minisplit/request/"+request.form['minisplit']
          message = json.dumps(command)
          mqtt_pub.single(topic, message, hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
        except BaseException as e:
            flash("Error updating Minisplit","warning")
            logger.debug("MQTT minisplit failed to publish: "+str(e))
        return redirect(url_for('facility.minisplit'))

    r = redis.Redis()
    roomtemp={}
    roomtemp["archer"]='--'
    roomtemp["foyer"]='--'
    roomtemp["class"]='--'
    roomtemp["first"]='--'
    roomtemp["av"]='--'
    roomtemp["hamshack"]='--'
    roomtemp["textiles"]='--'
    roomtemp["lounge"]='--'
    roomtemp["offices"]='--'

    minisplits=[]
    now=datetime.datetime.now()
    utc = dateutil.tz.gettz('UTC')
    eastern = dateutil.tz.gettz('US/Eastern')
    for m in (r.keys("minisplit/*")):
        ms = r.get(m)
        j = json.loads(ms)
        if (j['override_end'] != ""):
            ovend_obj = datetime.datetime.strptime(j['override_end'], '%a %b %d %H:%M:%S %Y')
            axx=ovend_obj.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)
            ovend=ago.ago(axx,now)
        else:
            ovend=["","",""]
        dt_obj = datetime.datetime.strptime(j['time'], '%a %b %d %H:%M:%S %Y')

        axx=dt_obj.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)
        acl=ago.ago(axx,now)

        msu =  normalize_temp(j['managed_setpoint_unoccupied']) if 'managed_setpoint_unoccupied' in j else 0
        os =  normalize_temp(j['override_setpoint']) if 'override_setpoint' in j else 0
        minisplits.append({
            'name': m.decode('utf-8').replace("minisplit/",""),
            'rawSetPoint': j['setpoint'],
            'setpoint': normalize_temp(j['setpoint']),
            'roomTemp': j['roomTemp'],
            'mode': j['mode'],
            'power': j['power'],
            'managed': j['managed'],
            'managed_setpoint': normalize_temp(j['managed_setpoint']),
            'managed_setpoint_unoccupied': msu,
            'override_setpoint': os,
            'override_time': j['override_time'],
            'ir_interval': j['ir_interval'] if 'ir_interval' in j else 0,
            'fan': j['fan'],
            'ipaddr': j['ip'],
            'rssid': j['rssid'],
            'fwversion': j['fw'],
            'lastupdate':acl[0],
            'lastupdate2':acl[1],
            'override_end':ovend[0],
            'override_end_ago':ovend[1],
            'operating':j['operating'] if 'operating' in j else 0
            })
        print (j)
        print (minisplits)
        roomtemp[ m.decode('utf-8').replace("minisplit/minisplit-","")] = j['roomTemp']
    return render_template('minisplits.html',minisplits=minisplits,roomtemp=roomtemp,temperatures=temperatures)

def register_pages(app):
	app.register_blueprint(blueprint)
