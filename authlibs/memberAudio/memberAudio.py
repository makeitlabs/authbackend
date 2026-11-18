# vim:tabstop=2:shiftwidth=2:expandtab

from ..templateCommon import *

from authlibs import accesslib

from authlibs.ubersearch import ubersearch
from authlibs import membership
from authlibs import payments
from authlibs.waivers.waivers import cli_waivers,connect_waivers
from authlibs.slackutils import automatch_missing_slack_ids,add_user_to_channel,send_slack_message
from authlibs.members.notices import send_all_notices
import base64
import random,string
import tempfile
import subprocess
import datetime
import subprocess
import os
import stat as statmod
from .. import ago
import math
from flask import send_from_directory
from werkzeug.utils import secure_filename


# ffmpeg  -hide_banner   -i Bradley.Goodman  -f s16le -acodec pcm_s16le -b:a 22050  -t 2 Bradley.Goodman.pcm 2>&1  | grep Duration | sed 's/\s*Duration: \(.*\), start.*/\1/g'
# ffmpeg  -hide_banner  -y -t 7 -i Bradley.Goodman.tmp  -f s16le -acodec pcm_s16le -b:a 22050  -t 2 Bradley.Goodman.pcm 

# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("memberAudio", __name__, template_folder='templates', static_folder="static",url_prefix="/memberAudio")



@blueprint.route('/', methods=['GET'])
@login_required
def audio():
    s = Subscription.query.filter(current_user.id == Subscription.member_id).one_or_none()
    plan = (s.plan if s else current_user.plan or "").lower()
    is_pro = bool(plan and "pro" in plan)

    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberAudioPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberAudioPath')
    
    hascurrent = False
    if folderPath and is_pro:
      fn = os.path.join(folderPath, current_user.member)
      hascurrent = os.path.exists(fn + ".pcm")

    return render_template('audio.html',
                           member=current_user,
                           is_pro=is_pro,
                           hascurrent=hascurrent,
                           nickname=current_user.nickname or '',
                           plates=current_user.plates or '',
                           phone=current_user.phone or '')


@login_required
@blueprint.route('/get', methods=['GET'])
def getAudio():
    s = Subscription.query.filter(current_user.id == Subscription.member_id).one_or_none()
    plan = (s.plan if s else current_user.plan or "").lower()
    if not (plan and "pro" in plan):
      flash("Entrance Audio is only available to Pro members", "danger")
      return redirect(url_for("memberAudio.audio"))
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberAudioPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberAudioPath')
    if not folderPath:
      flash("MemberAudio path not configured in INI file","danger")
      return redirect(url_for("memberAudio.audio"))

    fn = os.path.join(folderPath,current_user.member)
    if not os.path.exists(fn+".pcm"):
      flash("No audio has been uploaded","danger")
      return redirect(url_for("memberAudio.audio"))

    #  ffmpeg -f s16le -ar 16000 -ac 1 -i /var/www/memberAudio/Bradley.Goodman.pcm -f wav pipe:1
    try:
        wavdata=subprocess.check_output(['ffmpeg','-f','s16le','-ar','16000','-ac','1','-i',fn+'.pcm','-f','wav','pipe:1'])
    except:
      flash("Error decoding stored audio","danger")
      return redirect(url_for("memberAudio.audio"))

    return Response(
                response=wavdata,
                mimetype='audio/wav',
                status=200
            )

@login_required
@blueprint.route('/delete', methods=['GET'])
def deleteAudio():
    s = Subscription.query.filter(current_user.id == Subscription.member_id).one_or_none()
    plan = (s.plan if s else current_user.plan or "").lower()
    if not (plan and "pro" in plan):
      flash("Entrance Audio is only available to Pro members", "danger")
      return redirect(url_for("memberAudio.audio"))
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberAudioPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberAudioPath')
    if not folderPath:
      flash("MemberAudio path not configured in INI file","danger")
      return redirect(url_for("memberAudio.audio"))

    fn = os.path.join(folderPath,current_user.member)
    if not os.path.exists(fn+".pcm"):
      flash("No audio has been uploaded","danger")
      return redirect(url_for("memberAudio.audio"))

    os.remove(fn+".pcm")
    flash("Deleted entrance audio", "success")
    return redirect(url_for("memberAudio.audio"))

@blueprint.route('/setNickname', methods=['POST'])
@blueprint.route('/setProfile', methods=['POST'])
@login_required
def setNickname():
    updated = []
    if 'nickname' in request.form:
        current_user.nickname = request.form['nickname'].strip() or None
        updated.append("Nickname")
    if 'plates' in request.form:
        current_user.plates = request.form['plates'].strip() or None
        updated.append("License Plates")
    if 'phone' in request.form:
        current_user.phone = request.form['phone'].strip() or None
        updated.append("Phone")

    if updated:
        db.session.commit()
        flash(f"Updated {', '.join(updated)}", "success")
    return redirect(url_for("memberAudio.audio"))

@blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    s = Subscription.query.filter(current_user.id == Subscription.member_id).one_or_none()
    plan = (s.plan if s else current_user.plan or "").lower()
    if not (plan and "pro" in plan):
      flash("Entrance Audio is only available to Pro members", "danger")
      return redirect(url_for("memberAudio.audio"))
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberAudioPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberAudioPath')
    if not folderPath:
      flash("MemberAudio path not configured in INI file","danger")
      return redirect(url_for("memberAudio.audio"))

    if request.method != 'POST':
        flash('No audio file uploaded', 'danger')
        return redirect(url_for("memberAudio.audio"))
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No audio file uploaded', 'danger')
            return redirect(url_for("memberAudio.audio"))
        f= request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if f.filename == '':
            flash('No selected file', 'danger')
            return redirect(url_for("memberAudio.audio"))
        if f:
            fn = os.path.join(folderPath,current_user.member)
            #fn = os.path.join(folderPath,f.filename)
            f.save(fn+".tmp")
            cmd = ['ffmpeg','-hide_banner','-y','-t','7','-i',fn+'.tmp','-f','s16le','-acodec','pcm_s16le','-ac','1','-ar','16000',fn+'.pcm']
            if (subprocess.call(cmd)==0):
                flash("File saved","success")
            else:
                flash("Could not parse audio file","danger")
            try:
                os.remove(fn+".tmp")
            except:
                pass
            return redirect(url_for('memberAudio.audio'))
    flash("No file posted", 'danger')
    return redirect(url_for('memberAudio.audio'))

def register_pages(app):
	app.register_blueprint(blueprint)

