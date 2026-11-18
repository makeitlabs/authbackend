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
from  urllib.parse import quote,unquote
import random,string
import tempfile
import subprocess
import datetime
import hashlib
import os
import stat as statmod
from .. import ago
import math
from flask import send_from_directory,send_file,after_this_request
from werkzeug.utils import secure_filename

import paramiko,tempfile


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("memberFolders", __name__, template_folder='templates', static_folder="static",url_prefix="/memberFolders")


def getFolderConfig(member=current_user):
    config = {}
    error = None
    if current_app.config['globalConfig'].Config.has_option('MemberFolders','method'):
        config['method'] = current_app.config['globalConfig'].Config.get('MemberFolders','method')
    else:
        return (None,"Internal Error: Member folder method undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','user'):
        config['user'] = current_app.config['globalConfig'].Config.get('MemberFolders','user')
    else:
        return (None,"Internal Error: Member folder user undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','password'):
        config['password'] = current_app.config['globalConfig'].Config.get('MemberFolders','password')
    else:
        return (None,"Internal Error: Member folder password undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','server'):
        config['server'] = current_app.config['globalConfig'].Config.get('MemberFolders','server')
    else:
        return (None,"Internal Error: Member folder server undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','base'):
        config['base'] = current_app.config['globalConfig'].Config.get('MemberFolders','base')
    else:
        return (None,"Internal Error: Member folder base undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','cache'):
        config['cache'] = current_app.config['globalConfig'].Config.get('MemberFolders','cache')
    else:
        return (None,"Internal Error: Member folder cache undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','folderSecret'):
        config['folderSecret'] = current_app.config['globalConfig'].Config.get('MemberFolders','folderSecret')
    else:
        config['folderSecret'] = None

    if config['cache'][-1] != '/': config['cache']+= "/"

    if (member is None):
        return (config,None)

    if (member.memberFolder is None) or (member.memberFolder.strip() == ""):
        return (None,"Please ask an administrator to set up your member folder")

    if not os.path.isdir(config['cache']):
        return (None,"Internal Error: Cache Directory does not exist")

    return (config,None)


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

@blueprint.route('/folder', methods=['GET','POST'])
@login_required
def folder():
  #print ("ROOT FOLDER")
  return infolder("")

@blueprint.route('/folder/', methods=['GET','POST'])
@blueprint.route('/folder', methods=['GET','POST'])
@blueprint.route('/folder/<path:folder>', methods=['GET','POST'])
@login_required
# This is the entry point for a specific user and their own folder
def infolder(folder=""):
    return member_folder(folder,current_user)

# This is the entry point for a specific user and their own folder
#@blueprint.route('/sharedfolder/{string:member}/{string:secret}/<path:folder>', methods=['GET'])
@blueprint.route('/sharedfolder/<string:member>/<string:secret>/<path:folder>', methods=['GET'])
@login_required
def sharedfolder(folder,secret=None,member=None):
    logger.warning(f"Got folder {folder}")
    folder = folder.rstrip("/")
    m = Member.query.filter(Member.member == member).one_or_none()
    if m is None:
      flash("Invalid member","warning")
      return redirect(url_for("index"))
    if current_app.config['globalConfig'].Config.has_option('MemberFolders','folderSecret'):
        sharedSecret = current_app.config['globalConfig'].Config.get('MemberFolders','folderSecret')
    else:
      flash("Shared folders not configured","warning")
      return redirect(url_for("index"))

    hashstring = f"{sharedSecret}|{m.id}|{folder}"
    h = hashlib.sha224()
    h.update(str(hashstring).encode())
    actual = h.hexdigest()
    if (secret != actual):
      flash("Invalid Request","warning")
      logger.warning(f"Shared folder failed for {m.member} folder {folder} got {secret} neeeded {actual}")
      return redirect(url_for("index"))
    return member_folder(folder,m,asshared=True)

# Public, Open for Plasma
@blueprint.route('/allFolders', methods=['GET','POST'])
@login_required
def allFolders():
    return member_folder(None,None)

@login_required
# This is the entry point for a specific user and their own folder
def infolder(folder=""):
    return member_folder(folder,current_user)

# This is the worker function for any member or foler
# "As Shared" will give shared links
def member_folder(folder,member,asshared=False):
    if folder is None:
        (config,error) = getFolderConfig(member=None)
        path = config['base']+"/"
        folder = ""
    else:
        folder = folder.rstrip("/")
        #print ("INFOLDER",folder)
        if folder.find("../") != -1 or folder.find("/..") != -1:
          flash("Invalid Filename","warning")
        (config,error) = getFolderConfig(member=member)
        if (error is not None):
          flash(error,"warning")
          return redirect(url_for("index"))
        path = config['base']+"/"+member.memberFolder+"/"+folder
    files = []

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','folderSecret'):
        sharedSecret = current_app.config['globalConfig'].Config.get('MemberFolders','folderSecret')
    else:
      sharedSecret = None

    setShared=0



    try:
        with paramiko.Transport((config['server'],22)) as transport:
            transport.connect(None,config['user'],config['password'])
            with paramiko.SFTPClient.from_transport(transport) as sftp:
                if request.form and 'setShared' in request.form:
                    sftp.file(path+"/.shared",mode="w").write(request.form['setShared'])
                try:
                    contents = sftp.file(path+"/.shared").read()
                    setShared=int(contents)
                except:
                    setShared=0

                if ((setShared == 0) and (asshared == True)):
                    flash("No read permissions for this folder")
                    return redirect(url_for("index"))

                for entry in sftp.listdir_attr(path):
                    if entry.filename == '.sharing':
                        setShared=1;
                    if entry.filename.startswith("."): continue
                    mode = entry.st_mode
                    #print ("ENTRY",entry)
                    #print ("ENTRY",entry.attr,entry.filename)
                    #print ("ENTRY",mode)
                    #print ("ENTRY",dir(entry))
                    ext = entry.filename.split(".")[-1]
                    created = datetime.datetime.fromtimestamp(entry.st_mtime)
                    (ago1, ago2, ago3) = ago.ago(created,datetime.datetime.now())
                    fullpath = folder+"/"+entry.filename

                    sharedurl=""
                    if sharedSecret is not None and member is not None:
                        if (mode & statmod.S_IFDIR):
                            hashstring = f"{sharedSecret}|{member.id}|{fullpath}"
                        else:
                            hashstring = f"{sharedSecret}|{member.id}|{folder}"
                        h = hashlib.sha224()
                        h.update(str(hashstring).encode())
                        actual = h.hexdigest()
                        if (mode & statmod.S_IFDIR):
                            sharedurl = (url_for('memberFolders.sharedfolder',member=member.member,secret=actual,folder=fullpath))
                        else:
                            sharedurl = (url_for('memberFolders.downloadShared',filename=fullpath,secret=actual,member=member.member))
                    else:
                        sharedurl = ""

                    files.append({
                        'name':entry.filename,
                        'size':entry.st_size,
                        'sizeText':sizeunit(entry.st_size),
                        'ago1':ago1,
                        'ago2':ago2,
                        'ago3':ago3,
                        'type':"",
                        'ext':ext,
                        'dir': True if (mode & statmod.S_IFDIR) else False,
                        'path':fullpath,
                        'lastmod':entry.st_mtime,
                        'sharedurl':sharedurl
                      })
    except BaseException as e:
        flash(f"Failed {e} path {path} folder {folder}","warning")
        return redirect(url_for("index"))


    sharedlink = None
    if asshared == False and sharedSecret is not None and member is not None:
        hashstring = f"{sharedSecret}|{member.id}|{folder}"
        h = hashlib.sha224()
        h.update(str(hashstring).encode())
        actual = h.hexdigest()
        sharedlink = (url_for('memberFolders.sharedfolder',member=member.member,secret=actual,folder=folder))
        logger.warning(f"Calculated Shared folder as {actual} hashstring \"{hashstring}\"")

    top = folder.split("/")
    if folder == "":
      up=None
    elif len(top)==1:
      up=""
    else:
      up = "/"+("/".join(top[:-2]))

    if asshared == True:
        uploadLink=url_for('memberFolders.uploadshared_file2',member=member.member,secret=actual,folder=folder)
    else:
        uploadLink=url_for('memberFolders.upload_file2',folder=folder)
    return render_template('folder.html',up=up,folder=folder,member=member,
            asshared=asshared,files=sorted(files,key=lambda item: item['lastmod'],
                reverse=True),sharedlink=sharedlink,
                setShared=setShared,uploadLink=uploadLink)


@blueprint.route('/download/<path:filename>', methods=['GET'])
@login_required
def download(filename):
    return download_member(filename,current_user)

@blueprint.route('/view/<path:filename>', methods=['GET'])
@login_required
def view(filename):
    return download_member(filename,current_user,view=True)

@blueprint.route('/shareddownload/<string:member>/<string:secret>/<path:filename>', methods=['GET'])
@login_required
def downloadShared(filename,secret=None,member=None):
    filename = filename.rstrip("/")
    if filename.find("../") != -1 or filename.find("/..") != -1:
      flash("Invalid Filename","warning")
      return redirect(url_for("memberFolders.folder",folder=""))
    m = Member.query.filter(Member.member == member).one_or_none()
    if m is None:
      flash("Invalid member","warning")
      return redirect(url_for("index"))
    if current_app.config['globalConfig'].Config.has_option('MemberFolders','folderSecret'):
        sharedSecret = current_app.config['globalConfig'].Config.get('MemberFolders','folderSecret')
    else:
      flash("Shared folders not configured","warning")
      return redirect(url_for("index"))

    folder = "/".join(os.path.split(filename)[0:-1])
    hashstring = f"{sharedSecret}|{m.id}|{folder}"
    h = hashlib.sha224()
    h.update(str(hashstring).encode())
    actual = h.hexdigest()
    if (secret != actual):
      flash("Invalid Request","warning")
      logger.warning(f"Download Shared folder failed for {m.member} folder {folder} got {secret} neeeded {actual} hashstring \"{hashstring}\"")
      return redirect(url_for("index"))
    return download_member(filename,m,asshared=True)

def download_member(filename,member=current_user,asshared=False,view=False):
    @after_this_request
    def delete_after(response):
        try:
            os.remove(tempfilePath)
        except:
            pass
        return response

    filename = filename.rstrip("/")
    if filename.find("../") != -1 or filename.find("/..") != -1:
      flash("Invalid Filename","warning")
      return redirect(url_for("memberFolders.folder",folder=""))
    (config,error) = getFolderConfig(member=member)
    if (error is not None):
      flash(error,"warning")
      return redirect(url_for("index"))
    folder = "/".join(os.path.split(filename)[0:-1])
    path = config['base']+"/"+member.memberFolder+"/"+filename
    folderpath = config['base']+"/"+member.memberFolder+"/"+folder
    fn = os.path.split(path)[-1]
    files = []
    ext = filename.split(".")[-1]
    tempfileName = next(tempfile._get_candidate_names())+"."+ext
    tempfilePath = config['cache']+"/"+tempfileName
    path = config['base']+"/"+member.memberFolder+"/"+filename
    with paramiko.Transport((config['server'],22)) as transport:
        transport.connect(None,config['user'],config['password'])
        with paramiko.SFTPClient.from_transport(transport) as sftp:
            try:
                contents = sftp.file(folderpath+"/.shared").read()
                setShared=int(contents)
            except:
                setShared=0

            if ((setShared == 0) and (asshared == True)):
                flash("No read permissions for this folder")
                return redirect(url_for("index"))
            sftp.get(path,tempfilePath)

    ##XX = send_file(tempfilename,attachment_filename=fn,as_attachment=True)
   
    print  ("SENDING",config['cache'], fn)
    #return redirect(url_for("memberFolders.infolder"))
    ## return XX
    return send_from_directory(config['cache'], tempfileName, attachment_filename=fn, as_attachment=(not view))

@blueprint.route('/uploaded', methods=['GET'])
@blueprint.route('/uploaded/', methods=['GET'])
@blueprint.route('/uploaded/<path:folder>', methods=['GET'])
@login_required
def uploaded(folder=""):
    m = request.args.get("message")
    if m is not None and m.strip() != "" :
        flash(m)
    return infolder(folder=folder)

def createMemberFolder(user):
  try:
    foldername = user.member.replace("."," ")
    (config,error) = getFolderConfig(None)
    if (error is not None):
      logger.error(f"Error getting member folder config {error}")
      return 

    path = config['base']+"/"+foldername
    if path.find("../") != -1 or path.find("/..") != -1:
      logger.error(f"Bad member folder pathname {path}")
      return 

    try:
        with paramiko.Transport((config['server'],22)) as transport:
            transport.connect(None,config['user'],config['password'])
            with paramiko.SFTPClient.from_transport(transport) as sftp:
                try:
                    sftp.stat(path)
                    logger.error(f"Member Folder {path} already exists")
                except:
                    sftp.mkdir(path)
                    user.memberFolder = foldername
                    logger.info(f"Created {path} for {user.member}")
    except BaseException as e:
        logger.error(f"Create Member Folder {path} Error: {e}")
  except BaseException as e:
    logger.error(f"Create Member Folder {user.member} Error: {e}")

@blueprint.route('/createFolder', methods=['GET', 'POST'])
@login_required
def createFolder():
    (config,error) = getFolderConfig()
    if (error is not None):
      flash(error,"warning")
      return redirect(url_for("index"))

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

    filename = secure_filename(request.form['newname'])
    path = config['base']+"/"+current_user.memberFolder+"/"+folder+filename

    try:
        with paramiko.Transport((config['server'],22)) as transport:
            transport.connect(None,config['user'],config['password'])
            with paramiko.SFTPClient.from_transport(transport) as sftp:
                sftp.mkdir(path)
        flash("Folder Created","success")
    except BaseException as e:
        flash(f"Folder Create Error: {e}","danger")
    return redirect(url_for('memberFolders.infolder', folder=srcfolder))

@blueprint.route('/upload2', methods=['POST'])
@blueprint.route('/upload2/', methods=['POST'])
@blueprint.route('/upload2/<path:folder>', methods=['POST'])
@blueprint.route('/upload2', methods=['POST'])
@login_required
def upload_file2(folder=""):
    return upload_member_file2(folder,current_user)

@blueprint.route('/uploadshared2/<string:member>/<string:secret>/<path:folder>', methods=['POST'])
@login_required
def uploadshared_file2(member,secret,folder):
    if folder.find("../") != -1 or folder.find("/..") != -1:
      return json.dumps({'folder':folder,'message': "Invalid Filename"}),200
    m = Member.query.filter(Member.member == member).one_or_none()
    if m is None:
      return json.dumps({'folder':folder,'message': "Invalid Member"}),200
    if current_app.config['globalConfig'].Config.has_option('MemberFolders','folderSecret'):
        sharedSecret = current_app.config['globalConfig'].Config.get('MemberFolders','folderSecret')
    else:
      return json.dumps({'folder':folder,'message': "Not configured for shared access"}),200

    folder = folder.rstrip("/")
    hashstring = f"{sharedSecret}|{m.id}|{folder}"
    h = hashlib.sha224()
    h.update(str(hashstring).encode())
    actual = h.hexdigest()
    if (secret != actual):
      logger.warning(f"Upload Shared folder failed for {m.member} folder {folder} got {secret} neeeded {actual}")
      return json.dumps({'folder':folder,'message': "Invalid Request/No Access"}),200
    return upload_member_file2(folder,m,asshared=True)

def upload_member_file2(folder,member,asshared=False):
    folder = folder.rstrip("/")
    (config,error) = getFolderConfig()
    if (error is not None):
      flash(error,"warning")
      return redirect(url_for("index"))

    #print ("FOLDER IS",folder)

    if folder != "":
      if not folder.endswith("/"):
        #print ("AMMENDING FOLDER")
        folder += "/"
    if folder.find("../") != -1 or folder.find("/..") != -1:
      flash("Invalid Filename","warning")
      return redirect(url_for("memberFolders.folder",folder=""))

    uploaded_files = request.files.getlist('file')

    if not uploaded_files:
        return json.dumps({'folder':folder,'message': "No files"}),200

    # Replace 'uploads' with the path where you want to save the uploaded files
    upload_folder = 'uploads'
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    uploadlist=[]
    for file in uploaded_files:
        if file.filename == '':
            return json.dumps({'folder':folder,'message': "No files"}),200

        # DO UPLOAD 
        filename = secure_filename(file.filename)
        #print ("SAVE TO",filename)
        tempfileName = next(tempfile._get_candidate_names())
        tempfilePath = config['cache']+tempfileName
        file.save(tempfilePath)

        path = config['base']+"/"+member.memberFolder+"/"+folder+filename
        try:
            with paramiko.Transport((config['server'],22)) as transport:
                transport.connect(None,config['user'],config['password'])
                with paramiko.SFTPClient.from_transport(transport) as sftp:
                    print("SFTP",tempfilePath,path)
                    checkpath = config['base']+"/"+member.memberFolder+"/"+folder+".shared"
                    try:
                        contents = sftp.file(checkpath).read()
                        #logger.warn(f"Contents \"{contents}\"")
                        setShared=int(contents)
                    except BaseException as e:
                        #logger.warn(f"Upload error folder {checkpath}.shared error {e}")
                        setShared=0

                    #logger.warn(f"Sharing Path {folder} {setShared} AsShared {asshared}")
                    if ((setShared < 2) and (asshared == True)):
                        return json.dumps({'folder':folder,'message': "No upload permission"}),200
                    elif ((setShared == 2) and (asshared == True)):
                        try:
                            sftp.stat(path)
                            return json.dumps({'folder':folder,'message': "Can't overwrite existing file"}),200
                        except:
                            pass
                    sftp.put(tempfilePath,path)
            os.remove(tempfilePath)
            uploadlist.append(f"Uploaded {file.filename}")
        except BaseException as e:
            uploadlist.append(f"Error {filename}: {e}")

        # file.save(os.path.join(upload_folder, file.filename))

    return json.dumps({'folder':folder,'message': 'Uploaded: '+", ".join(uploadlist)}), 200


@blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():

    (config,error) = getFolderConfig()
    if (error is not None):
      flash(error,"warning")
      return redirect(url_for("index"))

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
            tempfileName = next(tempfile._get_candidate_names())
            tempfilePath = config['cache']+tempfileName
            file.save(tempfilePath)

            path = config['base']+"/"+current_user.memberFolder+"/"+folder+filename
            try:
                with paramiko.Transport((config['server'],22)) as transport:
                    transport.connect(None,config['user'],config['password'])
                    with paramiko.SFTPClient.from_transport(transport) as sftp:
                        print("SFTP",tempfilePath,path)
                        sftp.put(tempfilePath,path)
                os.remove(tempfilePath)
                flash("File saved","success")
            except BaseException as e:
                flash(f"Upload error: {e}","danger")
            return redirect(url_for('memberFolders.infolder', folder=srcfolder))
    flash("No file posted")
    return redirect(url_for('memberFolders.infolder', folder=srcfolder))

def register_pages(app):
	app.register_blueprint(blueprint)

