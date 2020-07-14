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
from datetime import datetime
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

def get_mqtt_opts(app):
  Config = ConfigParser.ConfigParser({})
  Config.read('makeit.ini')
  mqtt_opts={}
  mqtt_base_topic = Config.get("MQTT","BaseTopic")
  mqtt_opts['hostname'] = Config.get("MQTT","BrokerHost")
  mqtt_opts['port'] = Config.getint("MQTT","BrokerPort")
  if Config.has_option("MQTT","keepalive"):
      mqtt_opts['keepalive']=Config.getint("MQTT","keepalive")
  if Config.has_option("MQTT","SSL") and Config.getboolean("MQTT","SSL"):
      mqtt_opts['tls']={}
      mqtt_opts['tls']['ca_certs'] = Config.get('MQTT_SSL', 'ca_certs')
      mqtt_opts['tls']['certfile'] = Config.get('MQTT_SSL', 'certfile')
      mqtt_opts['tls']['keyfile'] = Config.get('MQTT_SSL', 'keyfile')

      if Config.has_option('MQTT_SSL', 'tls_version'):
          mqtt_opts['tls']['tls_version'] = Config.get('MQTT_SSL', 'tls_version')

      if Config.has_option('MQTT_SSL', 'ciphers'):
          mqtt_opts['tls']['ciphers'] = Config.get('MQTT_SSL', 'ciphers')

  if Config.has_option("MQTT","username"):
      mqtt_opts['auth']={'username':app.globalConfig.Config.get("MQTT","username"),'password':app.globalConfig.Config.get("MQTT","password")}
  slack_token = Config.get('Slack','BOT_API_TOKEN')
  return (mqtt_base_topic,mqtt_opts,slack_token)
if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--command",help="Special command",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    app=authbackend_init(__name__)

    with app.app_context():
      # The callback for when the client receives a CONNACK response from the server.
      (base_topic,opts,slack_api_token) = get_mqtt_opts(app)
      sc = SlackClient(slack_api_token)

      for m in Node.query.all():
          x =m.mac
          ip=None
          mac = x[0:2]+":"+ x[2:4]+":"+ x[4:6]+":"+ x[6:8]+":"+ x[8:10]+":"+x[10:12]
          for xx in [v.strip() for v in subprocess.Popen(["/usr/sbin/arp","-n"],stdout=subprocess.PIPE).stdout.readlines()]:
              sp = xx.split()
              if sp[2] == mac:
                  ip = sp[0]
          print m.name,mac,ip
          if ip:
            p=subprocess.call(["/bin/ping","-c1",ip])
            if p==0:
		eastern = dateutil.tz.gettz('US/Eastern')
		utc = dateutil.tz.gettz('UTC')
		now = datetime.utcnow()
		#now.replace(tzinfo=None).astimezone(utc).replace(tzinfo=None)
		#now.astimezone(utc).replace(tzinfo=None)
                m.last_ping=now
      db.session.commit();
