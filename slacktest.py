#!/usr/bin/python3
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
from slack_sdk import WebClient as SlackClient
import json
import configparser,sys,os
import paho.mqtt.client as mqtt
import paho.mqtt.subscribe as sub
from datetime import datetime
from authlibs.init import authbackend_init, createDefaultUsers
import requests,urllib
import logging, logging.handlers
from  authlibs import eventtypes
from slack_sdk.rtm import RTMClient

Config = configparser.ConfigParser({})
Config.read('makeit.ini')
bot_api_token = Config.get('Slack','BOT_API_TOKEN')
admin_api_token = Config.get('Slack','ADMIN_API_TOKEN')

OPENED=False
@RTMClient.run_on(event='open')
def onopen(**payload):
    print ("Opened",payload)
    global OPENED
    global rtmclient
    OPENED=True
    rtmclient.stop()

@RTMClient.run_on(event='error')
def onopen(**payload):
    print ("ERROR",payload)
    global OPENED
    global rtmclient
    OPENED=True
    rtmclient.stop()

if __name__ == '__main__':
        parser=argparse.ArgumentParser()
        parser.add_argument("--command",help="Special command",action="store_true")
        (args,extras) = parser.parse_known_args(sys.argv[1:])

        print ("ADMIN API TOKEN",admin_api_token)
        bot = SlackClient(bot_api_token)
        #if sc1.rtm_connect():
        #  print "RTM connected on BOT"
        #else:
        #  print "RTM Connection Failed"
        #  sys.exit(1)
        rtmclient = RTMClient(token=bot_api_token)

        print ("BOT API TOKEN",bot_api_token)
        res = bot.api_call(
          api_method="chat.postMessage",
          json={
              "channel":"U03126YLY",
              "text":"Bot Test Message"
          }
        )
        sc = SlackClient(admin_api_token)
        res = bot.chat_postMessage(
          channel="U03126YLY",
          text="Admin Test Message2"
          )
        res = sc.api_call(
          api_method="chat.postMessage",
          json={
              "channel":"U03126YLY",
              "text":"Admin Test Message"
            }
          )
        next_cursor=None
        while True:
          res = sc.conversations_list(
          cursor=next_cursor,
          exclude_archived=True
          )
          if not res['ok']:
            print ("conversaitons.list failed ",res)
            sys.exit(1)
          for x in res['channels']:
            if x['is_channel']:
              print (x['name'],x['id'])
            pass
          if 'response_metadata' not in res or 'next_cursor' not in res['response_metadata']:
            break
          next_cursor = res['response_metadata']['next_cursor']
          if next_cursor.strip() == "": break
          print ("NEXT CUROSR IS",next_cursor)
          
        # fake-resource-users
        res = sc.conversations_join(
        channel="CTN7EK3A9"
        )
        res = sc.conversations_join(
        channel="C014U9VPH16"
        )
        print (res)

        try:
            # Okay if this fails
            res = sc.conversations_invite(
            channel="CTN7EK3A9",
            users="U03126YLY"
            )
        except BaseException as e:
            print ("Invite failed - PROBABLY OKAY: ",e)


        """ 
        Now we will try the RTM connection that the bot uses
        """

        print ("Opening RTM")
        rtmclient.start()
        print ("RTM Stopped")
         
