#vim:tabstop=2:expandtab

# Command Line Interface

from datetime import datetime
import random,string
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from authlibs.db_models import db, ApiKey,  Role, UserRoles, Member, Resource, AccessByMember
from authlibs.payments import cli_updatepayments
from authlibs.membership import cli_syncmemberpayments
from authlibs.slackutils import cli_slacktest
from authlibs.ubersearch import cli_ubersearch
from autoplot.autoplot import cli_autoplot
from authlibs.api import api
from flask_sqlalchemy import SQLAlchemy
from .init import GLOBAL_LOGGER_LEVEL
from .slackutils import cli_slack,cli_slack_add_all_to_channels
import getpass
from .prostore import prostore
from .waivers.waivers import cli_waivers_connect, cli_waivers, cli_fix_waiver_types, cli_econtacts
from .members.notices import cli_member_notices

import logging
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)

def do_help(cmd=None,**kwargs):
    for x in sorted(commands): print ("  ",commands[x]['usage'])

def addadmin(cmd,**kwargs):
  admin_role = Role.query.filter(Role.name=='Admin').first()
  if not admin_role:
      admin_role = Role(name='Admin')
  user = Member(member=cmd[1],email=cmd[1]+"@makeitlabs.com",password=kwargs['app'].user_manager.hash_password(cmd[2]),email_confirmed_at=datetime.utcnow())
  db.session.add(user)
  user.roles.append(admin_role)
  db.session.commit()
  kwargs['app'].logger.debug("ADD USER "+str(cmd[1]))

def deleteadmin(cmd,**kwargs):
  Member.query.filter(User.email==cmd[1]).delete()
  db.session.commit()

def changepassword(cmd,**kwargs):
  user = Member.query.filter(Member.member.like(cmd[1])).one()
  print ("Set password for %s - %s" % (user.member,user.email))
  if len(cmd) <3:
      pw1=getpass.getpass("Password:")
      pw2=getpass.getpass("Reenter :")
      if pw1 != pw2:
          print ("Password mismatch")
          return
      user.password=kwargs['um'].hash_password(pw2)
  else:
      user.password=kwargs['um'].hash_password(cmd[2])
  db.session.commit()

def activate(cmd,**kwargs):
  user = Member.query.filter(Member.email==cmd[1]).first()
  user.email_confirmed_at = datetime.utcnow()
  db.session.commit()

def deactivate(cmd,**kwargs):
  user = Member.query.filter(Member.email==cmd[1]).first()
  db.session.commit()

def changekey(cmd,**kwargs):
  user = User.query.filter(User.email==cmd[1]).first()
  user.api_key=cmd[2]
  print ("Set",user.email,user.api_key)
  db.session.commit()

def revoke(cmd, **kwargs):
    x=UserRoles.query.join(Member)
    x = x.join(Role)
    x = x.filter(Member.member.ilike(cmd[1]))
    x = x.filter(Role.name.ilike(cmd[2]))
    x = x.one()
    db.session.delete(x)
    db.session.commit()

def grant(cmd, **kwargs):
    member = Member.query.filter(Member.member.ilike(cmd[1])).one()
    member.roles.append(Role.query.filter(Role.name.ilike(cmd[2])).one())
    db.session.commit()

def showadmins(cmd,**kwargs):
    #for x in Role.query.join(UserRoles).join(Member).add_column(Member.member).all():
    for x in db.session.query(Member.member).outerjoin(UserRoles).outerjoin(Role).add_column(Role.name).filter(Role.id!=None).all():
        print (x)
  
commands = {
	"addadmin":{
		'usage':"addadmin {username} {password}  -- Add adimin",
		'cmd':addadmin
	},
	"addapikey":{
		'usage':"addapikey {name} {username} [password]  -- Add API user w/ login token",
		'cmd':api.cli_addapikey
	},
	"changeapikey":{
		'usage':"change {name} {password}   -- Chance API key password",
		'cmd':api.cli_changeapikey
	},
	"deleteapikey":{
		'usage':"deleteapikey {name}  -- Delete API key password",
		'cmd':api.cli_deleteapikey
	},
	"listapikeys":{
		'usage':"listapikeys  -- Show API keys",
		'cmd':api.cli_listapikeys
	},
	"listadmins":{
		'usage':"listadmins -- show admin users",
		'cmd':showadmins
	},
	"passwd":{
		'usage':"passwd {memberid} [password]-- Change password",
		'cmd':changepassword
	},
	"changekey":{
		'usage':"changekey -- Change API key",
		'cmd':changekey
	},
	"help":{
		'usage':"listadmins -- show admin users",
		'cmd':do_help
	},
	"deleteadmin":{
		'usage':"deleteadmin -- Delete admin account",
		'cmd':deleteadmin
	},
	"updatepayments":{
		'usage':"updatepayments -- Update payment data",
		'cmd':cli_updatepayments
	},
	"memberpaysync":{
		'usage':"memberpaysync [--test] [--force] [--help]  -- Reconcile payment and member data",
		'cmd':cli_syncmemberpayments
	},
	"grant":{
		'usage':"grant {memberid} {priv} -- Grant a Backend GUI Privlage to user",
		'cmd':grant
	},
	"revoke":{
		'usage':"revoke {memberid} {priv} -- Revoke a Backend GUI Privlage to user",
		'cmd':revoke
	},
	"activate":{
		'usage':"activate {memberid} -- Activate a GUI account (Confirm email, activate)",
		'cmd':activate
	},
	"deactivate":{
		'usage':"deactivate {memberid} -- Dectivate a GUI account",
		'cmd':deactivate
	},
	"slack":{
		'usage':"slack -- Match slack users to members",
		'cmd':cli_slack
	},
	"slack_all_channels":{
		'usage':"slack_all_channels -- Add all users to resource channels",
		'cmd':cli_slack_add_all_to_channels
	},
	"querytest":{
		'usage':"querytest {member} -- Test DB Query",
		'cmd':api.cli_querytest
	},
	"updatewaivers":{
		'usage':"updatewaivers -- Update waiver data from smartwaivers",
		'cmd':cli_waivers
	},
	"loadwaiverecontacts":{
		'usage':"loadwaiverecontacts -- Update waiver Emergency Contacts",
		'cmd':cli_econtacts
	},
	"fixwaivers":{
		'usage':"fixwaivers -- Migrate waivers from v0.7 to v0.8",
		'cmd':cli_fix_waiver_types
	},
	"connectwaivers":{
		'usage':"connectwaivers -- Connect waivers with member records",
		'cmd':cli_waivers_connect
	},
	"cron":{
		'usage':"cron -- Do nightly cron job",
		'cmd':api.cli_cron
	},
	"prostore_migrate":{
		'usage':"prostore_migrate -- Migrate Prostore v0.8",
		'cmd':prostore.migrate
	},
	"notices":{
		'usage':"notices -- Process member account notifications",
		'cmd':cli_member_notices
	},
	"slacktest":{
		'usage':"slacktest -- Send slack test",
		'cmd':cli_slacktest
	},
	"ubersearch":{
		'usage':"ubersearch {searchstr} -- Try ubersearch",
		'cmd':cli_ubersearch
	},
	"autoplot":{
		'usage':"autoplot -- Autoplot Payments",
		'cmd':cli_autoplot
	}
}


def cli_command(cmd,**kwargs):
  if len(cmd)==0:
    return do_help()

  if cmd[0] in commands:
      with kwargs['app'].app_context():
        return (commands[cmd[0]]['cmd'](cmd,**kwargs))
	
  do_help()
	
