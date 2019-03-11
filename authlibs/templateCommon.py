"""
vim:tabstop=2:expandtab
This stuff will get loaded VERBATIM in the header of each authlib module
It is used to generalize stuff that should be common between all modules
It should only be used in modules like authlibs/example/example.py
And should be included via: 

from ..templateCommon import *
"""

# Common includes

import pprint,sys
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint, Markup
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from db_models import Member, db, Resource, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, \
    Logs, ApiKey, Tool, KVopt, Node, NodeConfig, Blacklist, accessLevelToString, UsageLog
from functools import wraps
import dateutil.tz
import json
from utilities import _safestr as safestr
from json import loads as json_load
from json import dumps as json_dump
import utilities as authutil
from sqlalchemy import and_, or_, func, case


# Set-up actual database logging

from authlibs import eventtypes
# Set-up Python module logging
import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)
