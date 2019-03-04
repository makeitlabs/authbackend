import inspect,sys
#vim:tabstop=2:expandtab

class RATTBE_LOGEVENT_UNKNOWN:
    id= 0
    desc= 'Unknown Event'

class RATTBE_LOGEVENT_COMMENT:
    id=1
    desc="Comment"


class RATTBE_LOGEVENT_CONFIG_OTHER:
    id=1000
    desc='Other Event'

class RATTBE_LOGEVENT_CONFIG_NEW_MEMBER_MANUAL:
    id=1001
    desc='Created New Member Manual'

class RATTBE_LOGEVENT_CONFIG_NEW_MEMBER_PAYSYS:
    id=1002
    desc='Created New Member from Pay System'

class RATTBE_LOGEVENT_CONFIG_PAY_MEMBER_IMPORT_ERR:
    id=1003
    desc='Payment Import Error'

class RATTBE_LOGEVENT_CONFIG_PAY_MEMBER_REASSIGN:
    id=1005
    desc='Payment Reassignment'

class RATTBE_LOGEVENT_MEMBER_TAG_ASSIGN:
    id=1006
    desc='Tag Assigned to Member'

class RATTBE_LOGEVENT_MEMBER_TAG_UNASSIGN:
    id=1007
    desc='Tag Unassigned to Member'

class RATTBE_LOGEVENT_MEMBER_ACCSSS_ENABLED:
    id=1008
    desc='Member Access Enabled'

class RATTBE_LOGEVENT_MEMBER_ACCSSS_DISABLED:
    id=1009
    desc='Member Access Disabled'

class RATTBE_LOGEVENT_MEMBER_WAIVER_ACCEPTED:
    id=1010
    desc='Waiver Accepted'

class RATTBE_LOGEVENT_MEMBER_PRIVILEGE_GRANTED:
    id=1011
    desc='Member Privilege Granted'

class RATTBE_LOGEVENT_MEMBER_PRIVILEGE_REVOKED:
    id=1012
    desc='Member Privilege Revoked'

class RATTBE_LOGEVENT_MEMBER_RESOURCE_LOCKOUT:
    id=1013
    desc='Member temporarily suspended from resource'

class RATTBE_LOGEVENT_MEMBER_RESOURCE_UNLOCKED:
    id=1014
    desc='Member Resource suspension removed'

class RATTBE_LOGEVENT_SYSTEM_OTHER:
    id=2000
    desc='Other System Event'

class RATTBE_LOGEVENT_SYSTEM_WIFI:
    id=2001
    desc='Wifi Status'

class RATTBE_LOGEVENT_SYSTEM_POWER_LOST:
    id=2002
    desc='Power Loss'
		slack_icon=':zzz:'

class RATTBE_LOGEVENT_SYSTEM_POWER_RESTORED:
    id=2003
    desc='Power Restored'
		slack_icon=':bulb:'

class RATTBE_LOGEVENT_SYSTEM_POWER_SHUTDOWN:
    id=2004
    desc='Shutdown'
		slack_icon=':zzz:'

class RATTBE_LOGEVENT_SYSTEM_POWER_OTHER:
    id=2005
    desc='Other Power Event'
		slack_icon=':lightning:'



class RATTBE_LOGEVENT_TOOL_OTHER:
    id=3000
    desc='Other Tool Event'

class RATTBE_LOGEVENT_TOOL_ISSUE:
    id=3001
    desc='Other Tool Issue'
		slack_icon=":exclamation:"

class RATTBE_LOGEVENT_TOOL_SAFETY:
    id=3002
    desc='Tool Safety'
		slack_icon=":alert:"

class RATTBE_LOGEVENT_TOOL_ACTIVE:
    id=3003
    desc='Tool Active'
		slack_icon=":arrow_forward:"

class RATTBE_LOGEVENT_TOOL_INACTIVE:
    id=3004
    desc='Tool Inactive'
		slack_icon=":double_vertical_bar:"

class RATTBE_LOGEVENT_TOOL_LOCKOUT_PENDING:
    id=3005
    desc='Tool Lockout Pending'

class RATTBE_LOGEVENT_TOOL_LOCKOUT_LOCKED:
    id=3006
    desc='Tool Locked-out'
		slack_icon=":lock:"

class RATTBE_LOGEVENT_TOOL_LOCKOUT_UNLOCKED:
    id=3007
    desc='Tool Unlocked'
		slack_icon=":unlock:"

class RATTBE_LOGEVENT_TOOL_LOCKOUT_OTHER:
    id=3008
    desc='Lockout other'


class RATTBE_LOGEVENT_TOOL_POWERON:
    id=3009
    desc="Tool Powered On"
		slack_icon=":bulb:"

class RATTBE_LOGEVENT_TOOL_POWEROFF:
    id=3010
    desc="Tool Powered Off"
		slack_icon=":zzz:"

class RATTBE_LOGEVENT_TOOL_LOGIN_COMBO:
    id=3011
    desc="Login (via. combo/passcode)"
		slack_icon=":arrow_right:"

class RATTBE_LOGEVENT_TOOL_PROHIBITED:
    id=3012
    desc="Access Denied"
		slack_icon=":no_entry:"

class RATTBE_LOGEVENT_TOOL_LOGIN:
    id=3013
    desc="Logged in"
		slack_icon=":arrow_right:"

class RATTBE_LOGEVENT_TOOL_COMBO_FAILED:
    id=3014
    desc="Incorrect Passcode attempt"
		slack_icon=":no_entry:"

class RATTBE_LOGEVENT_TOOL_LOGOUT:
    id=3015
    desc="Logged-out"
		slack_icon=":arrow_left:"

class RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED:
    id=4000
    desc='Resource access granted'
		slack_icon=":thumbs_up:"

class RATTBE_LOGEVENT_RESOURCE_ACCESS_REVOKED:
    id=4001
    desc='Resource access granted'
		slack_icon=":thumbs_down:"

class RATTBE_LOGEVENT_RESOURCE_ACCESS_XXX:
    id=4002
    desc='Resource access granted'

class RATTBE_LOGEVENT_RESOURCE_PRIV_CHANGE:
    id=4004
    desc='Resource privilege change'
		slack_icon=":level_slider:"




def get_event_slack_icons():
		icons={}
    for (name,cl) in inspect.getmembers(sys.modules[__name__], inspect.isclass):
			if hasattr(cl,"slack_icon"):
        icons[cl.id]=cl.slack_icon

		return icons
				
def get_events():
		"""
		print RATTBE_LOGEVENT_UNKNOWN
		print RATTBE_LOGEVENT_UNKNOWN.id
		print RATTBE_LOGEVENT_UNKNOWN.desc
		print dir(__package__)
		print __package__.__doc__
		"""

    events_by_id={}
    for (name,cl) in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        events_by_id[cl.id]=cl.desc
    return events_by_id

if __name__=="__main__":
    print get_events()
		print get_event_slack_icons()
