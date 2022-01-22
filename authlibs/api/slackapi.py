# vim:shiftwidth=2:expandtab

from ..templateCommon import *

from authlibs import accesslib

from authlibs.ubersearch import ubersearch
from authlibs import membership
from authlibs import payments
from authlibs.waivers.waivers import cli_waivers,connect_waivers
#import slackapi
import random,string

def get_tool_by_name(toolname):
  t = Tool.query.filter(Tool.name.ilike(toolname)).one_or_none()
  if t: return t
  return Tool.query.filter(Tool.short.ilike(toolname)).one_or_none()

  
# Returns an error string OR a tool
def make_sure_tool_arm(toolname,member):
  t = get_tool_by_name(toolname)
  if not t: return ":question: No tool found"

  r = Resource.query.filter(Resource.id == t.resource_id)
  r = r.outerjoin(AccessByMember,((AccessByMember.member_id == member.id) & (AccessByMember.resource_id == Resource.id)))
  r = r.add_column(AccessByMember.level)
  r = r.one_or_none()
  if not r: return ":question: No tool found"
  if r.level is None: return ":no_entry: No privileges on that resource type"
  if (r.level < AccessByMember.LEVEL_ARM): return ":no_entry: Insufficent privileges on that resource type"

  return t

def lock(cmd,member):
  if len(cmd) < 3:
    return ":question: Usage: `lock {tool} {reason}`"
  r =  make_sure_tool_arm(cmd[1],member)
  if type(r)==str: return r
  reasonstr = " ".join(cmd[2:])
  r.lockout=reasonstr
  authutil.log(eventtypes.RATTBE_LOGEVENT_TOOL_LOCKOUT_LOCKED.id,tool_id=r.id,message=r.lockout,doneby=member.id,commit=0)
  node = Node.query.filter(Node.id == r.node_id).one()
  authutil.send_tool_lockout(r.name,node.mac,r.lockout)
  db.session.commit()
  return ":lock: %s now locked." % r.name

def unlock(cmd,member):
  if len(cmd) < 2:
    return ":question: Usage: `unlock {tool}`"
  r =  make_sure_tool_arm(cmd[1],member)
  if type(r)==str: return r
  r.lockout=None
  authutil.log(eventtypes.RATTBE_LOGEVENT_TOOL_LOCKOUT_UNLOCKED.id,tool_id=r.id,message=r.lockout,doneby=member.id,commit=0)
  node = Node.query.filter(Node.id == r.node_id).one()
  authutil.send_tool_remove_lockout(r.name,node.mac)
  db.session.commit()
  return ":unlock: %s now unlocked." % r.name

def helpcmd(cmd,member):
  outstr = ""
  for x in admincmds:
    if 'desc' in x:
      outstr += x['desc']+"\n"
  return outstr
  

admincmds= [
  {
    'command':'lock',
    'desc':'`lock {tool} {reason}` - Lock a tool',
    'handler':lock
  },
  {
    'command':'luck',
    'desc':'`luck {tool} {reason}` - Wish a tool best of luck',
    'handler':lambda a,b: ":four_leaf_clover:"
  },
  {
    'command':'unlock',
    'desc':'`unlock {tool}` - Unlock a tool',
    'handler':unlock
  },
  {
    'command':'help',
    'handler':helpcmd
  }
]
  
def slack_admin_api(cmd,member):
  cmdmatch=[]
  if len(cmd) < 1:
    return help(cmd,member)

  for x in admincmds:
    if x['command'].startswith(cmd[0]):
      cmdmatch.append(x)

  if len(cmdmatch)>1:
    outstr = "Ambigious - could be:\n"
    for x in cmdmatch:
      outstr += "%s\n" % x['desc']
    return outstr

  if len(cmdmatch)==1:
    return cmdmatch[0]['handler'](cmd,member)
    
  return ":question: Unknown command `%s`" % cmd[0]
