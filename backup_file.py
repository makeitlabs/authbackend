#!/bin/python3
# vim:tabstop=2:shiftwidth=2:expandtab
# Nightly Backup and updates


from authlibs.templateCommon import *
from authlibs.init import authbackend_init
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
    parser=argparse.ArgumentParser()
    parser.add_argument("--verbose","-v",help="verbosity",action="count")
    parser.add_argument("--debug","-d",help="verbosity",action="count")
    parser.add_argument("--nopayment",help="Do not update payment and waiver data",action="store_true")
    parser.add_argument("--noupload",help="Do not send backups to AWS",action="store_true")
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
    if not args.noupload:
        s3 = boto3.client('s3',
            aws_access_key_id= aws_token,
            aws_secret_access_key=aws_secret_key)

    if args.verbose: 
        print ("* Sending backups to Amazon")
        for f in extras:
            fn = f.split("/")[-1]
            if args.verbose: "BACKUP",f,fn
            s3.upload_file(f,aws_bucket,fn)

        
