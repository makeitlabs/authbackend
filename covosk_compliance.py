#!/usr/bin/python3
"""
vim:tabstop=2:expandtab:shiftwidth=2:softtabstop=2
MakeIt Labs Authorization System, v0.4

This is a daemon only used to log stuff via MQTT
"""

from authlibs.eventtypes import *
import sqlite3, re, time
from authlibs.db_models import db,  Role, UserRoles, Member, Resource, AccessByMember, Logs, Tool, UsageLog, Node
import argparse
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from flask_sqlalchemy import SQLAlchemy
from authlibs import utilities as authutil
from slack_sdk import WebClient as SlackClient
import json
import configparser,sys,os
import paho.mqtt.client as mqtt
import paho.mqtt.subscribe as sub
from datetime import datetime,timedelta
from authlibs.init import authbackend_init, createDefaultUsers
import requests,urllib
import logging, logging.handlers
from  authlibs import eventtypes
import subprocess
import dateutil
import dateutil.tz
import tempfile
import urllib
import io


## SETUP LOGGING

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logger=logging.getLogger()
handler = logging.handlers.RotatingFileHandler(
    "/tmp/mqtt_dameon.log", maxBytes=(1048576*5), backupCount=7)
handler.setLevel(logging.DEBUG)
format = logging.Formatter("%(asctime)s:%(levelname)s:%(module)s:%(message)s")
handler.setFormatter(format)
ch = logging.StreamHandler()
format = logging.Formatter("%(module)s:%(levelname)s:%(message)s")
ch.setFormatter(format)
ch.setLevel(logging.DEBUG)

logger.addHandler(ch)
logger.addHandler(handler)

Config = configparser.ConfigParser({})
Config.read('makeit.ini')
slack_token = Config.get('Slack','BOT_API_TOKEN')
cam_username = Config.get('cameras','api_username')
cam_password = Config.get('cameras','api_password')
cam_id = Config.get('cameras','camera_id')
cam_addr = Config.get('cameras','camera_addr')
cam_slackchan = Config.get('cameras','slackchan')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--command",help="Special command",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    app=authbackend_init(__name__)

    with app.app_context():
      # The callback for when the client receives a CONNACK response from the server.
      sc = SlackClient(slack_token)

      members={}
      index=0

      eastern = dateutil.tz.gettz('US/Eastern')
      utc = dateutil.tz.gettz('UTC')
      fmtime = datetime.now() - timedelta(minutes=33)
      grace = datetime.now() - timedelta(minutes=3)
      for m in Logs.query.filter(Logs.event_type == RATTBE_LOGEVENT_MEMBER_ENTRY_ALLOWED.id,Logs.time_reported > fmtime,Logs.time_reported < grace).all():
        if m.member_id not in members: 
            members[m.member_id]=[]
        members[m.member_id].append(m.time_reported)
      for m in members.keys():
        member = Member.query.filter(Member.id==m).one_or_none()
        mn = "Member id {0}".format(m)
        c=0
        if member:
            mn = member.member
            fmtime = datetime.now() - timedelta(days=1)
            c =  Logs.query.filter(Logs.event_type == RATTBE_LOGEVENT_MEMBER_KIOSK_ACCEPTED.id,Logs.member_id == member.id,Logs.time_reported > fmtime).count()
        print (m,mn,c)
        if c == 0:
            for t in members[m]:
                t=t.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)
                print (":alert: {0} has violated kiosk protocol at {1}".format(mn,t))
                tc= t.strftime("%Y-%m-%dT%H:%M:%S.000")
                fn = "tmpvideo_{0}_{1}".format(os.getpid(),index)
                index +=1
                url = "http://{username}:{password}@{addr}/hls/{camid}.ts?pos={tc}&duration=20&lo".format(tc=tc,username=cam_username,password=cam_password, addr=cam_addr,camid=cam_id)
                tt = open(fn+".ts","w")
                tt.write(urllib.urlopen(url).read())
                tt.close()
                subprocess.call(['ffmpeg','-i',fn+".ts",'-f','mp4',"authlibs/logs/static/kioskimages/"+fn+".mp4"])
                subprocess.call(['chmod','644',"authlibs/logs/static/kioskimages/"+fn+".mp4"])
                subprocess.call(['rm',fn+".ts"])
                print ("DONE")


                #ffmpeg -i riley.ts -f mp4 riley.mp4
            res = sc.chat_postMessage(
              channel=cam_slackchan,
              text=":alert: {0} has violated kiosk protocol {1}".format(mn,"https://auth.makeitlabs.com/authit/logs/static/kioskimages/"+fn+".mp4")
              )
            
