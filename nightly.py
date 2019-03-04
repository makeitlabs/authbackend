#!/usr/bin/python
# vim:tabstop=2:shiftwidth=2:expandtab
# Nightly Backup and updates


from authlibs.templateCommon import *
from authlibs.init import authbackend_init
import urllib2,urllib,requests
import argparse
from  datetime import datetime,timedelta
import random
import ConfigParser
import subprocess,os
import glob
import boto3
from stat import *


from authlibs import aclbackup

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
		parser.add_argument("--verbose","-v",help="verbosity",action="count")
		parser.add_argument("--debug","-d",help="verbosity",action="count")
		parser.add_argument("--nopayment",help="Do not update payment and waiver data",action="store_true")
		(args,extras) = parser.parse_known_args(sys.argv[1:])

    now = datetime.now()
    today=now.strftime("%Y-%m-%d")

    Config = ConfigParser.ConfigParser({})
    Config.read('makeit.ini')
    backup_dir = Config.get("backups","db_backup_directory")
    aws_token=Config.get("backups","aws_token")
    aws_secret_key=Config.get("backups","aws_secret_key")
    aws_bucket=Config.get("backups","aws_bucket")
    dbfile = Config.get("General","Database")
    logdbfile = Config.get("General","LogDatabase")
    acldir = Config.get("backups","acl_backup_directory")
    localurl = Config.get("backups","localurl")
    api_username = Config.get("backups","api_username")
    api_password = Config.get("backups","api_password")

    # Take Snapshot of databases
    if args.verbose: print "* Snapshotting databases"
    os.system("sqlite3 %s '.backup %s/%s-db.sq3'" % (dbfile,backup_dir,today))
    os.system("sqlite3 %s '.backup %s/%s-logdb.sq3'" % (logdbfile,backup_dir,today))

    # Run nightly payment/waiver update
    if not args.nopayment:
      if args.verbose: print "* Updating payment and waiver data"
      #os.system("curl http://%s:%s@%s/api/cron/nightly" % ( api_username,api_password,localurl))
      req = requests.Session()
      api_creds = (api_username,api_password)
      url = localurl+"/api/cron/nightly"
      r = req.get(url, auth=api_creds)
      if r.status_code != 200:
        print "WARNING - error in nightly cron API"

    # Make a backup of ACL lists for all resources, and generate reports of changes
    if args.verbose: print "* Backing up ACLs"
    aclbackup.do_update()

    # Prune old backup files
    now = datetime.now()
    if args.verbose: print "* Pruning old files"
    for d in (acldir,backup_dir):
      files = glob.glob(os.path.join(d,"*"))
      for f in files:
        mode = os.stat(f)
        ft=  datetime.fromtimestamp(mode.st_ctime)
        age = now-ft
        if age > timedelta(days=31):
          # File is too old - delete
          if args.verbose: print "DELETING ",f,now-ft
          os.unlink(f)

    # Send backups to Amazon S3 (and Glacier) storage
    s3 = boto3.client('s3',
      aws_access_key_id= aws_token,
      aws_secret_access_key=aws_secret_key)

    if args.verbose: print "* Sending backups to Amazon"
    for d in (acldir,backup_dir):
      files = glob.glob(os.path.join(d,today+"*"))
      for f in files:
        fn = f.split("/")[-1]
        if args.verbose: "BACKUP",f,fn
        #s3.put_object(Body=html, Key=fn,ContentType="text/html",Bucket=aws_bucket)
        s3.upload_file(f,aws_bucket,fn)

        
