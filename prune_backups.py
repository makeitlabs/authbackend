#!/usr/bin/python3
# vim:tabstop=2:shiftwidth=2:expandtab:softtabstop
# Nightly Backup and updates


from authlibs.templateCommon import *
from authlibs.init import authbackend_init
import urllib,requests
import argparse
from  datetime import datetime,timedelta
import random
import configparser
import subprocess,os
import glob
import boto3
from stat import *


from authlibs import aclbackup

if __name__ == '__main__':
    parser=argparse.ArgumentParser(usage="restore [{filenames...}]")
    parser.add_argument("--verbose","-v",help="verbosity",action="count")
    parser.add_argument("--debug","-d",help="verbosity",action="count")
    parser.add_argument("--show-prune",help="show what would be pruned",action="store_true")
    parser.add_argument("--do-prune",help="Prune files",action="store_true")
    parser.add_argument("--show-keep",help="show what would be kept",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    now = datetime.now()
    today=now.strftime("%Y-%m-%d")

    Config = configparser.ConfigParser({})
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


    # Send backups to Amazon S3 (and Glacier) storage
    s3 = boto3.resource('s3',
      aws_access_key_id= aws_token,
      aws_secret_access_key=aws_secret_key)
    bucket = s3.Bucket(aws_bucket)

    # List all files
    for f in bucket.objects.all():
        delta = now - f.last_modified.replace(tzinfo=None)
        if ((delta.days > 90) and (f.last_modified.day != 1)):
            if args.show_prune: print ("PRUNE: {1:10.10} {2:10d}   {0}".format(f.key,str(f.last_modified),f.size))
            if args.do_prune: 
              bucket.delete_objects(Delete={'Objects':[{'Key':f.key}]})
              print ("PRUNED: {1:10.10} {2:10d}   {0}".format(f.key,str(f.last_modified),f.size))
        else:
            if args.show_keep: print ("KEEP: {1:10.10} {2:10d}   {0}".format(f.key,str(f.last_modified),f.size))
