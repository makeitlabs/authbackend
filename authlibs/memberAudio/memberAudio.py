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
    if (s.plan != "pro"):
      flash("MemberAudio is only availble to Pro members")
      return redirect(url_for("index"))
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberAudioPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberAudioPath')
    if not folderPath:
      flash("MemberAudio path not configured in INI file","danger")
      return redirect(url_for("index"))
    return render_template('audio.html',member=current_user)



@blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    s = Subscription.query.filter(current_user.id == Subscription.member_id).one_or_none()
    if (s.plan != "pro"):
      flash("MemberAudio is only availble to Pro members")
      return redirect(url_for("index"))
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberAudioPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberAudioPath')
    if not folderPath:
      flash("MemberAudio path not configured in INI file","danger")
      return redirect(url_for("index"))

    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(url_for("memberAudio.audio",folder=srcfolder))
        f= request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if f.filename == '':
            flash('No selected file')
            return redirect(url_for("memberAudio.audio",folder=srcfolder))
        if f:
            fn = os.path.join(folderPath,current_user.member).encode('utf=8')
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
    flash("No file posted")
    return redirect(url_for('memberAudio.audio', folder=srcfolder))

def register_pages(app):
	app.register_blueprint(blueprint)

