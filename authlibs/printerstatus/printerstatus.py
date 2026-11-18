# vim:shiftwidth=2:expandtab

from ..templateCommon import *
import redis
import json
import requests
from flask import Response, abort, request

blueprint = Blueprint("printerstatus", __name__, template_folder='templates', static_folder="static", url_prefix="/printerstatus")
#printers/00m09d470802228 {"name": "MakeIt Left", "status": "RUNNING", "percent": 40, "min_remaining": 20, "reported": "2026-06-09T17:36:42.238514", "job": "AJ_HATHAWAY-Foxy"}
#printers/00M09D470802228 {"name": "MakeIt Left", "status": "FINISH", "percent": 100, "min_remaining": 0, "reported": "2026-06-15T09:45:55.293886", "job": "jay_briand-JASK\u00d3\u0141KA_MOLD"}
#printers/00M09D462500690 {"name": "MakeIt Right", "status": "FINISH", "percent": 100, "min_remaining": 0, "reported": "2026-06-15T09:45:06.713445", "job": "jay_briand-PRED8_VIBE_mold"}
#printers/0938aj632500655 {"name": "Gamera", "status": "FAILED", "percent": 0, "min_remaining": 0, "reported": "2026-06-09T17:36:42.425520", "job": "dose_divider3_v12"}
#printers/0938AJ632500655 {"name": "Gamera", "status": "FINISH", "percent": 100, "min_remaining": 0, "reported": "2026-06-15T09:45:36.165388", "job": "Tom_Doucet_P-T800_T_121_body"}
#printers/0948AB510700445 {"name": "Godzilla", "status": "IDLE", "percent": 0, "min_remaining": 0, "reported": "2026-06-09T22:11:14.196290", "job": ""}


@blueprint.route('/', methods=['GET'])
@login_required
def status():
    r = redis.Redis()
    printers = []
    
    for p in r.keys("printer/*"):
        p_data = r.get(p)
        if not p_data:
            continue
        try:
            j = json.loads(p_data)
        except json.JSONDecodeError:
            continue
            
        raw_status = j.get('status', 'IDLE').upper()
        if raw_status == 'RUNNING':
            mapped_status = 'running'
        elif raw_status == 'FAILED':
            mapped_status = 'error'
        else:
            mapped_status = 'idle'
            
        time_rem = j.get('min_remaining', 0)
        if time_rem > 0:
            time_remaining = f"{time_rem // 60}h {time_rem % 60}m" if time_rem >= 60 else f"{time_rem}m"
        else:
            time_remaining = None

        filename = j.get('job', None)
        if not filename:
            filename = None

        printers.append({
            'name': j.get('name', p.decode('utf-8').replace('printer/', '')),
            'serialno': p.decode('utf-8').replace('printer/', ''),
            'status': mapped_status,
            'progress': j.get('percent', 0),
            'time_remaining': time_remaining,
            'filename': filename,
            'error': 'Printer reported failure' if mapped_status == 'error' else None
        })
        
    # Sort printers by name so they appear consistently
    printers.sort(key=lambda x: x['name'])
    return render_template('printerstatus.html', printers=printers)

@blueprint.route('/cam/<string:serialno>', methods=['GET'])
@login_required
def cam(serialno):
    name = request.args.get('name', serialno)
    return render_template('printercam.html', serialno=serialno, name=name)

@blueprint.route('/cam_image/<string:serialno>', methods=['GET'])
@login_required
def cam_image(serialno):
    try:
        r = requests.get(f"http://printmon/images/{serialno}", timeout=5)
        return Response(r.content, mimetype=r.headers.get('content-type', 'image/jpeg'))
    except requests.RequestException:
        abort(502)

def register_pages(app):
    app.register_blueprint(blueprint)
