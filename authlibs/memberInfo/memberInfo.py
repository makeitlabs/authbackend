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


# magick input.jpg -resize "720x" -format png output.png


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("memberInfo", __name__, template_folder='templates', static_folder="static",url_prefix="/memberInfo")



@blueprint.route('/', methods=['GET'])
@login_required
def info():
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberPhotoPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberPhotoPath')
    if not folderPath:
      flash("MemberPhoto path not configured in INI file","danger")
      return redirect(url_for("index"))
    fn = os.path.join(folderPath,current_user.member)
    hascurrent =  os.path.exists(fn+".png")
    return render_template('photo.html',member=current_user,hascurrent=hascurrent,plates=current_user.plates)


@login_required
@blueprint.route('/get', methods=['GET'])
def getPhoto():
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberPhotoPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberPhotoPath')
    if not folderPath:
      flash("MemberAudio path not configured in INI file","danger")
      return redirect(url_for("index"))

    fn = os.path.join(folderPath,current_user.member)
    if not os.path.exists(fn+".png"):
      flash("No info has been uploaded","danger")
      return redirect(url_for("index"))

    try:
        with open(fn+".png","rb") as wd:
            pngdata =wd.read()
    except BaseException as e:
        flash(f"Error decoding stored photo: {e}","danger")
        return redirect(url_for("index"))

    return Response(
                response=pngdata,
                mimetype='image/png',
                status=200
            )

@login_required
@blueprint.route('/getMemberThumbnail/<int:mid>', methods=['GET'])
def getMemberThumbnail(mid):
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberPhotoPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberPhotoPath')
    if not folderPath:
      flash("MemberAudio path not configured in INI file","danger")
      return redirect(url_for("index"))

    member = Member.query.filter(Member.id == mid).one_or_none()
    if member is None:
        return Response(
                response="ID not found",
                status=404
            )
    fn = os.path.join(folderPath,member.member)
    if not os.path.exists(fn+".png"):
        return Response(
                    response="Photo not uploaded",
                    status=404
                )

    try:
        #with open(fn+".png","rb") as wd:
        #    pngdata =wd.read()
        pngdata=subprocess.check_output(['convert',fn+'.png','-resize','100x','-format','png','-'])
    except BaseException as e:
        flash(f"Error decoding stored photo: {e}","danger")
        return redirect(url_for("index"))

    return Response(
                response=pngdata,
                mimetype='image/png',
                status=200
            )
@blueprint.route('/setLicensePlates', methods=['POST'])
@login_required
def setLicensePlates():
    if 'plates' in request.form:
        #  " ".join("test\ntest2\ntest".split())
        current_user.plates = " ".join(request.form['plates'].strip().split())
        db.session.commit()
        flash("License Plates Updated")
    return redirect(url_for("memberInfo.info"))

@blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberPhotoPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberPhotoPath')
    if not folderPath:
      flash("MemberPhotoPath not configured in INI file","danger")
      return redirect(url_for("index"))

    if request.method != 'POST':
        flash('No photo file uploaded')
        return redirect(url_for("memberInfo.info"))
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No photo file uploaded')
            return redirect(url_for("memberInfo.info"))
        f= request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if f.filename == '':
            flash('No selected file')
            return redirect(url_for("memberInfo.info"))
        if f:
            fn = os.path.join(folderPath,current_user.member)
            #fn = os.path.join(folderPath,f.filename)
            # convert input.jpg -resize "720x" -format png output.png
            f.save(fn+".tmp")
            cmd = ['convert',fn+'.tmp','-quality','50','-resize','720x','-format','png',fn+'.png']
            if (subprocess.call(cmd)==0):
                flash("File saved","success")
            else:
                flash("Could not parse photo file - bad formet","danger")
            try:
                os.remove(fn+".tmp")
            except:
                pass
            return redirect(url_for('memberInfo.info'))
    flash("No file posted")
    return redirect(url_for('memberInfo.info'))

def register_pages(app):
	app.register_blueprint(blueprint)

