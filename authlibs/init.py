"""
vim:tabstop=2:expandtab
MakeIt Labs Authorization System, v0.4

Flask, Configuration, SQLAlchemy and Database Initialization

"""

from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app 
from flask_sqlalchemy import SQLAlchemy
import logging
import sys
import ConfigParser
from db_models import db,  Member, Role, defined_roles, ApiKey
from datetime import datetime
from werkzeug.contrib.fixers import ProxyFix
from flask_dance.consumer import oauth_authorized
from flask_dance.contrib.google import make_google_blueprint
from flask_dance.contrib.google import  google as google_flask
import requests
import logging.handlers

# SET THIS 
GLOBAL_LOGGER_LEVEL = logging.DEBUG
GLOBAL_LOGGER_LOGFILE = "/tmp/authit.log"


## SETUP LOGGING

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logger=logging.getLogger()
handler = logging.handlers.RotatingFileHandler(
    GLOBAL_LOGGER_LOGFILE, maxBytes=(1048576*5), backupCount=7)
handler.setLevel(GLOBAL_LOGGER_LEVEL)
format = logging.Formatter("%(asctime)s:%(levelname)s:%(module)s:%(message)s")
handler.setFormatter(format)
ch = logging.StreamHandler()
format = logging.Formatter("%(module)s:%(levelname)s:%(message)s")
ch.setFormatter(format)
ch.setLevel(GLOBAL_LOGGER_LEVEL)

logger.addHandler(ch)
logger.addHandler(handler)


from google_user_auth import authinit

# Load general configuration from file

def get_config():
    config={}
    defaults = {'ServerPort': 5000, 'ServerHost': '127.0.0.1'}
    ConfigObj = ConfigParser.ConfigParser(defaults)
    ConfigObj.read('makeit.ini')
    """
    This doesn't work for some reason???
    for s in ConfigObj.sections():
        config[s]={}
        for o in ConfigObj.options(s):
            print "GET",o
            config[s][o]=ConfigObj.get(s,o)
            print "GOT",o
    """
    return ConfigObj

def createDefaultRoles(app):
    for role in defined_roles:
      r = Role.query.filter(Role.name==role).one_or_none()
      if not r:
          r = Role(name=role)
          db.session.add(r)
    db.session.commit()

def createDefaultUsers(app):
    createDefaultRoles(app)
    """
    # Create default admin role and user if not present
    admin_role = Role.query.filter(Role.name=='Admin').first()
    if not User.query.filter(User.email == app.globalConfig.AdminUser).first():
        user = User(email=app.globalConfig.AdminUser,password=app.user_manager.hash_password(app.globalConfig.AdminPasswd),email_confirmed_at=datetime.utcnow())
        logger.debug("ADD USER "+str(user))
        db.session.add(user)
        user.roles.append(admin_role)
        db.session.commit()
    """
    # TODO - other default users?

class GlobalConfig(object):
  """ These are all Authbackend-Specifc. Reference via app.globalConfig 

      Anything in the ini file which is not explicitly stored as a variable here
      can be accessed at runtime with:

      app.globalConfig.Config.get("Category","itemname")
  """
  Config = get_config()
  ServerHost = Config.get('General','ServerHost')
  ServerPort = Config.getint('General','ServerPort')
  Database = Config.get('General','Database')
  AdminUser = Config.get('General','AdminUser')
  AdminPasswd = Config.get('General','AdminPassword')
  DeployType = Config.get('General','Deployment')
  DefaultLogin = Config.get('General','DefaultLogin')
  Debug = Config.getboolean('General','Debug')

  """ Extract MQTT settings here (So we don't have to do every time we kick """

  mqtt_opts={}
  mqtt_base_topic = Config.get("MQTT","BaseTopic")
  mqtt_host = Config.get("MQTT","BrokerHost")
  mqtt_port = Config.getint("MQTT","BrokerPort")
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


class ConfigClass(object):
  """ Many UPPSERCASE variables here are used by Flask directly.
      Variables can generally be reference three different ways:

      1. app.config.ServerHost
      2. app.config.Config.get('General,ServerHost')
      3. app.config.config['General']['SeverHost']

  """
  Config = get_config()
  ServerHost = Config.get('General','ServerHost')
  ServerPort = Config.getint('General','ServerPort')
  Database = Config.get('General','Database')
  LogDatabase = Config.get('General','LogDatabase')
  AdminUser = Config.get('General','AdminUser')
  AdminPasswd = Config.get('General','AdminPassword')
  DeployType = Config.get('General','Deployment')
  DEBUG = Config.getboolean('General','Debug')
  SECRET_KEY = Config.get('General','SecretKey')

  # Flask-User Settings
  USER_APP_NAME = 'Basic'
  USER_PASSLIB_CRYPTCONTEXT_SCHEMES=['pbkdf2_sha256']
  # Don;t want to include these, but it depends on them, so..
  USER_ENABLE_EMAIL = True        # Enable email authentication
  USER_ENABLE_USERNAME = False    # Disable username authentication
  USER_EMAIL_SENDER_NAME = USER_APP_NAME
  USER_EMAIL_SENDER_EMAIL = "noreply@example.com"

  # SQLAlchemy setting
  SQLALCHEMY_BINDS = {
          'main': "sqlite:///"+Database,
          'logs': "sqlite:///"+LogDatabase,
    }
  SQLALCHEMY_TRACK_MODIFICATIONS = False

  # Load Waiver system data from file
  waiversystem = {}
  waiversystem['Apikey'] = Config.get('Smartwaiver','Apikey')

def authbackend_init(name):
  app = Flask(name)
  app.config.from_object(__name__+'.ConfigClass')
  app.config['globalConfig'] = GlobalConfig()

  authinit(app)

  db.init_app(app)
  return app
