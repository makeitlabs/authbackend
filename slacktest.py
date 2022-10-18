#!/usr/bin/python2
"""
vim:tabstop=2:expandtab:shiftwidth=2
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
from authlibs.slackutils import automatch_missing_slack_ids,add_user_to_channel,send_slack_message
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

Config = ConfigParser.ConfigParser({})
Config.read('makeit.ini')
slack_api_token = Config.get('Slack','BOT_API_TOKEN')
admin_api_token = Config.get('Slack','ADMIN_API_TOKEN')

if __name__ == '__main__':
        parser=argparse.ArgumentParser()
        parser.add_argument("--command",help="Special command",action="store_true")
        (args,extras) = parser.parse_known_args(sys.argv[1:])

        print "ADMIN API TOKEN",admin_api_token
        sc1 = SlackClient(slack_api_token)
        #if sc1.rtm_connect():
        #  print "RTM connected on BOT"
        #else:
        #  print "RTM Connection Failed"
        #  sys.exit(1)

        print "API TOKEN",slack_api_token
        sc = SlackClient(admin_api_token)
        res = sc1.api_call(
          "chat.postMessage",
          channel="U03126YLY",
          text="Admin Test Message"
          )
        res = sc.api_call(
          "chat.postMessage",
          channel="U03126YLY",
          text="Bot Test Message"
          )
        next_cursor=None
        while True:
          res = sc.api_call(
          "conversations.list",
          cursor=next_cursor,
          exclude_archived=True
          )
          if not res['ok']:
            print "conversaitons.list failed ",res
            sys.exit(1)
          for x in res['channels']:
            if x['is_channel']:
              print x['name'],x['id']
            pass
          if 'response_metadata' not in res or 'next_cursor' not in res['response_metadata']:
            break
          next_cursor = res['response_metadata']['next_cursor']
          if next_cursor.strip() == "": break
          print "NEXT CUROSR IS",next_cursor
          
        # fake-resource-users
	print "TEST JOIN"
        res = sc.api_call(
        "conversations.join",
        channel="CTN7EK3A9"
        )
	print "TEST JOIN2"
        res = sc1.api_call(
        "conversations.join",
        channel="CTN7EK3A9"
        )
        print "JOIN2",res

	print "TEST INVITE"
        res = sc1.api_call(
        "conversations.invite",
        channel="CTN7EK3A9",
        users="U03126YLY"
        )
	print "TEST INVITE",res
