#!/usr/bin/python3
# vim:tabstop=2:shiftwidth=2:expandtab
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
import getpass
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet, InvalidToken


from authlibs import aclbackup


def decrypt_secret(salt,secret):
    # 1. Safely prompt the user for their password (masks input)
    user_password = getpass.getpass("Password: ").encode()

    # 2. Reconstruct the PBKDF2 key derivation using the original salt
    salt = bytes.fromhex(salt)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )

    # 3. Derive the key from the entered password
    key = base64.urlsafe_b64encode(kdf.derive(user_password))
    f = Fernet(key)

    # 4. Attempt to decrypt
    try:
        decrypted_message = f.decrypt(secret)
        return (decrypted_message.decode())
    except InvalidToken:
        print("Incorrect password. Access denied.")
        sys.exit(1)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(usage="restore [{filenames...}]")
    parser.add_argument("--verbose","-v",help="verbosity",action="count")
    parser.add_argument("--debug","-d",help="verbosity",action="count")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    now = datetime.now()
    today=now.strftime("%Y-%m-%d")

    Config = configparser.ConfigParser({})
    Config.read('makeit.ini')
    backup_dir = Config.get("backups","db_backup_directory")
    salt = Config.get("backups","restore_salt")
    aws_token = Config.get("backups","restore_aws_token")
    secret = Config.get("backups","restore_encrypted_secret").encode("utf-8")
    aws_secret_key=decrypt_secret(salt,secret)
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

    if extras:
      for f in extras:
        if args.verbose: print ("Restoring",f)
        try:
          bucket.download_file(f,f)
        except BaseException as e:
          print ("ERROR",f,e)
          sys.exit(1)
    else:
      # List all files
      for f in bucket.objects.all():
        print ("{1:10.10} {2:10d}   {0}".format(f.key,str(f.last_modified),f.size))
