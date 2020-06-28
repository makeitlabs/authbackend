#!/usr/bin/python2
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
from slackclient import SlackClient
import json
import ConfigParser,sys,os
import paho.mqtt.client as mqtt
import paho.mqtt.subscribe as sub
from datetime import datetime,timedelta
from authlibs.init import authbackend_init, createDefaultUsers
import requests,urllib,urllib2
import logging, logging.handlers
from  authlibs import eventtypes
import subprocess
import dateutil
import dateutil.tz


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

Config = ConfigParser.ConfigParser({})
Config.read('makeit.ini')
slack_token = Config.get('Slack','BOT_API_TOKEN')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--command",help="Special command",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    app=authbackend_init(__name__)

    with app.app_context():
      # The callback for when the client receives a CONNACK response from the server.
      sc = SlackClient(slack_token)

      members={}
      fmtime = datetime.now() - timedelta(days=1)
      for m in Logs.query.filter(Logs.event_type == RATTBE_LOGEVENT_MEMBER_ENTRY_ALLOWED.id,Logs.time_reported > fmtime).all():
        members[m.member_id]=True
      for m in members.keys():
        member = Member.query.filter(Member.id==m).one_or_none()
        mn = "Member id {0}".format(m)
        c=0
        if member:
            mn = member.member
            fmtime = datetime.now() - timedelta(days=1.5)
            c =  Logs.query.filter(Logs.event_type == RATTBE_LOGEVENT_MEMBER_KIOSK_ACCEPTED.id,Logs.member_id == member.id,Logs.time_reported > fmtime).count()
        print m,mn,c
        if c == 0:
            res = sc.api_call(
              "chat.postMessage",
              channel="C014U9VPH16",
              text=":alert: {0} has violated kiosk protocol".format(mn)
              )
            
