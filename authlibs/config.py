#!/usr/bin/env python
# Config stub that all modules can share, instead of reloading..

import configparser
import logging
import os


general = {}
payments = {}
pinpayments = {}
stripe = {}
smartwaiver = {}

# What if we just build one config object, instead?
Config = configparser.ConfigParser()
inifile='makeit.ini'
if 'AUTHIT_INI' in os.environ:
  inifile = os.environ['AUTHIT_INI']
Config.read(inifile)

if 'General' in Config.sections():
    for o in Config.options('General'):
        general[o] = Config.get('General',o)
     
if 'Payments' in Config.sections():
    for o in Config.options('Payments'):
        payments[o] = Config.get('Payments',o)

if 'Pinpayments' in Config.sections():
    for o in Config.options('Pinpayments'):
        pinpayments[o] = Config.get('Pinpayments',o)

if 'Stripe' in Config.sections():
    for o in Config.options('Stripe'):
        stripe[o] = Config.get('Stripe',o)

if 'Smartwaiver' in Config.sections():
     for o in Config.options('Smartwaiver'):
        smartwaiver[o] = Config.get('Smartwaiver',o)
     
def configLogger(l):
    l.basicConfig()
    l.setLevel(logger.DEBUG)

    
