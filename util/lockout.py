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

Config = ConfigParser.ConfigParser({})
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

	allowed=0
	denied=0
	already=0
	error=0
	with app.app_context():
		for d in AccessByMember.query.filter(AccessByMember.resource_id == 1).all():
			m = Member.query.filter(Member.id == d.member_id).one_or_none()
			if not m:
				print "ID",d.member_id,"NOT FOUND"
				error += 1
			else:
				f =  AccessByMember.query.filter((AccessByMember.resource_id == 22) & (AccessByMember.member_id == d.member_id)).one_or_none()
				if f:
					allowed += 1
					print "ALLOWED",f.member_id,m.member
				else:
					if not d.lockout_reason or d.lockout_reason == "":
						print "DENIED",m.member
						denied += 1
						#d.lockout_reason = "Covid-19 Training Required"
						db.session.delete(d)
					else:
						print "ALREADY DENIED",m.member
						already += 1
		db.session.commit()
	print "ALLOWED",allowed,"DENIED",denied,"ERROR",error,"ALREADY",already
