# vim:tabstop=2:expandtab:shiftwidth=2
from templateCommon import *
import accesslib

''' If "img" is missing - will not appear in index page, only menu '''

# "Importance" controls order in index page (icons) 
def get_raw_menu():
    return [
            {
                    'checkfunc':rm_check,
                    'url':url_for('authorize.authorize'),
                    'img':url_for("static",filename="menu_key.png"),
                    'title':"Authorize Members",
                    'alt':"Quick method for basic tool access",
                    'importance':1000
            },
            {
                    'url':url_for('members.members'),
                    'img':url_for("static",filename="office.png"),
                    'alt':"View, Create or Edit members and their access",
                    'title':"Members",
                    'importance':1010
            },
            {
                    'checkfunc':rm_check,
                    'privs':'RATT',
                    'url':url_for('members.update_backends'),
                    'title':"Backend Update ACLs"
            },
            {
                    'checkfunc':rm_check,
                    'privs':'RATT',
                    'url':url_for('resources.resources'),
                    'img':url_for("static",filename="building.png"),
                    'alt':"View, Create or Modify Resources Classifactions",
                    'title':"Resource Groups",
                    'importance':2000
            },
            {
                    'url':url_for('logs.logs'),
                    'img':url_for("static",filename="logs.png"),
                    'alt':"View Logs",
                    'title':"Logs",
                    'importance':1100
            },
            {
                    'privs':'RATT',
                    'checkfunc':rm_check,
                    'url':url_for('tools.tools'),
                    'img':url_for("static",filename="toolcfg.png"),
                    'alt':"Configure Tools",
                    'title':"Tools",
                    'importance':2000
            },
            {
                    'privs':'Useredit',
                    'url':url_for('waivers.waivers'),
                    'img':url_for("static",filename="contract.png"),
                    'alt':"View Waiver Data",
                    'title':"Waivers"
            },
            {
                    'privs':'Useredit',
                    'url':url_for('slack_page'),
                    'title':"Slack"
            },
            {
                    'privs':'Finance',
                    'url':url_for('payments.payments'),
                    'img':url_for("static",filename="finance.png"),
                    'alt':"View or Test Payment System integration",
                    'title':"Payments"
            },
            {
                    'privs':'Useredit',
                      'url':url_for('members.member_report'),
                    'title':"Member Reports"
            },
            {
                    'url':url_for('logout_soft'),
                    'title':"Logout (Soft)"
            },
            {
                    'url':url_for('prostore.bins'),
                    'title':"Pro Storage Bins"
            },
            {
                    'url':url_for('prostore.locations'),
                    'title':"Pro Storage Locations"
            },
            {
                    'privs':'Finance',
                    'url':url_for('reports.blacklist'),
                    'alt':"Ignored payments",
                    'title':"Blacklists"
            },
            {
                    'privs':'Admin',
                    'url':url_for('members.admin_page'),
                    'title':"Admin Roles",
                    'importance':2000
            },
            {
                    'privs':'RATT',
                    'url':url_for('nodes.nodes'),
                    'img':url_for("static",filename="rattcfg.png"),
                    'alt':"Physical RATT settings",
                    'title':"Node Configuration",
                    'importance':2000
            },
            {
                    'privs':'RATT',
                    'url':url_for('apikeys.apikeys'),
                    'title':"API Keys",
            },
            {
                    'privs':'RATT',
                    'url':url_for('kvopts.kvopts'),
                    'title':"Node Parameters",
            },
            {
                    'privs':'Admin',
                    'url':url_for('belog.belog'),
                    'title':"Backend Web Logs",
            },
            {
                    'privs':'Useredit',
                    'url':url_for('members.lookup_tag'),
                    'title':"Tag Lookup",
                    'alt':"Search for RFID Tag"
            }
    ]

def rm_check(user):
  if accesslib.user_is_authorizor(user,level=2): return True
  return False

def main_menu():
  result = []
  for m in get_raw_menu():
    allow = False
    if 'checkfunc' in m and m['checkfunc'](current_user):
      allow = True
    if 'privs' in m and  current_user.privs(m['privs']):
      allow = True
    if 'privs' not in m and 'checkfunc' not in m:
      allow = True
    if allow:
      result.append(m)
  return sorted(result,key=lambda x:x['title'])

def index_page():
  result = []
  for m in get_raw_menu():
    allow = False
    if 'importance' not in m: m['importance']="zzz"
    if 'checkfunc' in m and m['checkfunc'](current_user):
      allow = True
    elif 'privs' in m and current_user.privs(m['privs']):
      allow = True
    if 'privs' not in m and 'checkfunc' not in m:
      allow = True
    if allow:
      result.append(m)
  return sorted(result,key=lambda x:(str(x["importance"])+"-"+x['title']))
