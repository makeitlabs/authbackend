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
import os
import stat as statmod
from .. import ago
import math
from flask import send_from_directory
from werkzeug.utils import secure_filename


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("memberFolders", __name__, template_folder='templates', static_folder="static",url_prefix="/memberFolders")


def sizeunit(val):
  if val==0: return "0b"
  units=['b','k','M','G','T','P','E','Z']
  l = math.log10(val)
  i = int(math.floor(l/3))
  u = units[int(i)]
  r = i*3
  d = math.pow(10,r)
  #print val,l,i,val/d,u
  s = "{0:4.0f}{1}".format(round(val/d),u)
  #print val,"=",s
  return s

@blueprint.route('/folder', methods=['GET'])
@login_required
def folder():
  #print ("ROOT FOLDER")
  return infolder("")

@blueprint.route('/folder/', methods=['GET'])
@blueprint.route('/folder', methods=['GET'])
@blueprint.route('/folder/<path:folder>', methods=['GET'])
@login_required
def infolder(folder=""):
    #print ("INFOLDER",folder)
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberFolderPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberFolderPath')
    if not folderPath:
      flash("MemberFolderPath not configured in INI file","danger")
      return redirect(url_for("index"))
    if not current_user.memberFolder:
      flash("No Member Folder associated with this account. Please contact an administrator and tell them the name of your Member Folder","warning")
      return redirect(url_for("index"))
    if not os.path.isdir(folderPath):
      flash("NAS Path does not exist - Contact Administrator","danger")
      return redirect(url_for("index"))
    path = folderPath+"/"+current_user.memberFolder+"/"+folder
    if not os.path.isdir(path):
      flash("Member Folder does not exist - Contact Administrator","danger")
      return redirect(url_for("index"))
    files = []
    for fn in  os.listdir(path):
      if '/' in fn: next # Ain't got not time for that
      fp  = path+"/"+fn
      stat = os.stat(fp)
      #print ("MODE",hex(stat.st_mode))
      created = datetime.datetime.fromtimestamp(stat.st_mtime)
      #print (created)
      (ago1,ago2,ago3) = ago.ago(created,datetime.datetime.now())
      try:
        ft = "" # TOO SLOW!! subprocess.check_output(['file','-b',fp])
      except:
        ft = "??"
      #print ("File Type",ft)
      ext = fn.split(".")
      if len(ext) > 1:
        ext = ext[-1]
      else:
        ext=''
      if folder =="":
        fullpath=fn
      else:
        fullpath = folder+"/"+fn
      files.append({
        'name':fn,
        'size':stat.st_size,
        'sizeText':sizeunit(stat.st_size),
        'ago1':ago1,
        'ago2':ago2,
        'ago3':ago3,
        'type':ft,
        'ext':ext,
        'dir':statmod.S_ISDIR(stat.st_mode),
        'path':fullpath,
        'lastmod':stat.st_mtime
      })
    
    #print  (files)
    top = folder.split("/")
    #print ("FOLDER",folder,"TOP",top)
    if folder == "":
      up=None
    elif len(top)==1:
      up=""
    else:
      up = "/"+("/".join(top[:-1]))
    #print ("UP",up)
    return render_template('folder.html',up=up,folder=folder,member=current_user,files=files)


@blueprint.route('/download/<path:filename>', methods=['GET'])
@login_required
def download(filename):
    folderPath = None
    if current_app.config['globalConfig'].Config.has_option('General','MemberFolderPath'):
      folderPath = current_app.config['globalConfig'].Config.get('General','MemberFolderPath')
    if filename.find("..") != -1:
      flash("Error in file path","warning")
      return redirect(url_for("index"))
    if not folderPath:
      flash("MemberFolderPath not configured in INI file","danger")
      return redirect(url_for("index"))
    if not current_user.memberFolder:
      flash("No Member Folder associated with this account. Please contact an administrator and tell them the name of your Member Folder","warning")
      return redirect(url_for("index"))
    if not os.path.isdir(folderPath):
      flash("NAS Path does not exist - Contact Administrator","danger")
      return redirect(url_for("index"))
    path = folderPath+"/"+current_user.memberFolder
    #print ("GET",filename,"FROM",path)
    return send_from_directory(directory=path, filename=filename)

@blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    folder=""
    if request.form and 'folder' in request.form:
      folder = request.form['folder']
      srcfolder = folder
    #print ("FOLDER IS",folder)
    if folder != "":
      if not folder.endswith("/"):
        #print ("AMMENDING FOLDER")
        folder += "/"
    if folder.find("../") != -1 or folder.find("/..") != -1:
      flash("Invalid Filename","warning")
      return redirect(url_for("memberFolders.folder",folder=""))
    #print ("UPLOADING TO FOLDER",folder)
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(url_for("memberFolders.infolder",folder=srcfolder))
        file = request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(url_for("memberFolders.infolder",folder=srcfolder))
        if file:
            filename = secure_filename(file.filename)
            #print ("SAVE TO",filename)
            file.save("/tmp/bkg/"+ folder + filename)
            flash("File saved","success")
            return redirect(url_for('memberFolders.infolder', folder=srcfolder))
    flash("No file posted")
    return redirect(url_for('memberFolders.infolder', folder=srcfolder))

def register_pages(app):
	app.register_blueprint(blueprint)

