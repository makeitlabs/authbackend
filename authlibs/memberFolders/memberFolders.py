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


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("memberFolders", __name__, template_folder='templates', static_folder="static",url_prefix="/memberFolders")


def sizeunit(val):
  if val==0: return "Empty"
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
    path = folderPath+"/"+current_user.memberFolder
    if not os.path.isdir(path):
      flash("Member Folder does not exist - Contact Administrator","danger")
      return redirect(url_for("index"))
    files = []
    for fn in  os.listdir(path):
      if '/' in fn: next # Ain't got not time for that
      fp  = path+"/"+fn
      stat = os.stat(fp)
      print "MODE",hex(stat.st_mode)
      created = datetime.datetime.fromtimestamp(stat.st_mtime)
      print created
      (ago1,ago2,ago3) = ago.ago(created,datetime.datetime.now())
      try:
        ft = subprocess.check_output(['file','-b',fp])
      except:
        ft = "??"
      print "File Type",ft
      ext = fn.split(".")
      if len(ext) > 1:
        ext = ext[-1]
      else:
        ext='n/a'
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
        'lastmod':stat.st_mtime
      })
    
    print  files
    return render_template('folder.html',member=current_user,files=files)

@blueprint.route('/download/<path:filename>', methods=['GET'])
@login_required
def download(filename):
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
    path = folderPath+"/"+current_user.memberFolder
    print "GET",filename,"FROM",path
    return send_from_directory(directory=path, filename=filename)

def register_pages(app):
	app.register_blueprint(blueprint)
