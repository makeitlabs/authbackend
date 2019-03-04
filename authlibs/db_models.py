# Database models
#im:expandtab:tabstop=4
# Single file containing all required DB models, for now
from flask_sqlalchemy import SQLAlchemy
from flask_user import UserManager, UserMixin
import hashlib,zlib
from flask_login.mixins import AnonymousUserMixin
import random, string
from flask_dance.consumer.backend.sqla import SQLAlchemyBackend, OAuthConsumerMixin



defined_roles=['Admin','RATT','Finance','Useredit','HeadRM']

db = SQLAlchemy()

# This class mirrors the "member" class, but is used for 
# Anonymous (i.e. logged-out) sessions.
# NOT stored in DB. Must mimic stuff in "Member" class
class AnonymousMember(AnonymousUserMixin):
    member=None
    email=None

    # Anonymous users have no roles
    def privs(self,*roles):
        return False

    def effective_roles(self):
        return []

    def resource_roles(self):
        return []
	
		def is_arm(self):
				return False

# Members and their data
class Member(db.Model,UserMixin):
    __tablename__ = 'members'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    member = db.Column(db.String(50), unique=True)
    email = db.Column(db.String(50))
    alt_email = db.Column(db.String(50))
    firstname = db.Column(db.String(50))
    slack = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    phone = db.Column(db.String(50))
    plan = db.Column(db.String(50))	 # "Pro", "Hobbiest" - "ProDuo" - from stripe??
    access_enabled = db.Column(db.Integer(),default=0) # Defaults to "0" for new member - Waiver will make this non-zero - means no access
    access_reason = db.Column(db.String(50)) # If access_enabled is nonzero - access_reason will be a MANUAL reason for no access (empty means waiver-block)
    active = db.Column(db.Integer()) # Applies to membership AND GUI login (flask-user) set ONLY by program logic
    nickname = db.Column(db.String(50))
    stripe_name = db.Column(db.String(50))
    time_created = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    time_updated = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
    warning_sent = db.Column(db.DateTime(timezone=True))
    warning_level = db.Column(db.Integer()) 
    email_confirmed_at = db.Column(db.DateTime())
    membership = db.Column(db.String(50),nullable=True,unique=True)

    password = db.Column(db.String(255),nullable=True)
    roles= db.relationship('Role', secondary = 'userroles')

    # Returns "true" if use has at least one of the specified roles
    # Use this instead of "has_roles" - it treats "admin" like everyone
    def privs(self,*roles):
        if self.has_roles('Admin'): return True
        for x in roles:
            if x not in defined_roles:
                print("\"%s\" is not a defined role" % x)
            if self.has_roles(x): return True
        return False

    def get(self,id):
        return Member.query.filter(Member.member ==id).one()

    def effective_roles(self):
      roles=[]
      for r in defined_roles:
        if self.has_roles('Admin') or self.has_roles(r):
          roles.append(r)
        if self.has_roles('Finance') and 'Useredit' not in roles:
          roles.append("Useredit")
      return roles

    def get_id(self):
        """Return the email address to satisfy Flask-Login's requirements."""
        return self.member+"@makeitlabs.com"

    def is_arm(self):
				return AccessByMember.query.filter(AccessByMember.member_id == self.id,AccessByMember.level >= AccessByMember.LEVEL_ARM).count() >= 1

    def resource_roles(self):
        return [x[0] for x in db.session.query(Resource.name).join(AccessByMember,AccessByMember.resource_id == Resource.id).filter(AccessByMember.member_id == self.id,AccessByMember.level >= AccessByMember.LEVEL_ARM).all()]


class ApiKey(db.Model):
    __tablename__ = 'apikeys'
    __bind_key__ = 'main'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50),nullable=False)
    username = db.Column(db.String(50),nullable=False)
    password = db.Column(db.String(50),nullable=True)
    tool_id = db.Column(db.Integer(), db.ForeignKey('tools.id', ondelete='CASCADE'),nullable=True)

class Tool(db.Model):
    __tablename__ = 'tools'
    __bind_key__ = 'main'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    lockout = db.Column(db.String(100), nullable=True)
    short = db.Column(db.String(20), unique=True, nullable=True)
    node_id = db.Column(db.Integer(), db.ForeignKey('nodes.id', ondelete='CASCADE'))
    resource_id = db.Column(db.Integer(), db.ForeignKey('resources.id', ondelete='CASCADE'))

class AccessByMember(db.Model):
    __tablename__ = 'accessbymember'
    __bind_key__ = 'main'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id', ondelete='CASCADE'),nullable=False)
    resource_id = db.Column(db.Integer(), db.ForeignKey('resources.id', ondelete='CASCADE'),nullable=False)
    active = db.Column('is_active',db.Boolean(), nullable=False, server_default='1')
    time_created = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    time_updated = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
    comment = db.Column(db.String(255), nullable=True, server_default='')
    lockout_reason = db.Column(db.String(255), nullable=True) # If non-null, user locked-out of resource
    lockouts = db.Column(db.String(255), nullable=True, server_default='') # If non-null, user locked-out of resource (UNIMPLEMENTED)
    permissions = db.Column(db.String(255), nullable=True, server_default='')
    created_by = db.Column(db.String(25), nullable=False, server_default='admin')
    level = db.Column(db.Integer(),default=0)
    __table_args__ = (db.UniqueConstraint('member_id', 'resource_id', name='_member_resource_uc'),)


    ACCESS_LEVEL=['User','Trainer','ARM','RM','Admin']
    LEVEL_USER=0
    LEVEL_TRAINER=1
    LEVEL_ARM=2
    LEVEL_RM=3
    LEVEL_ADMIN=4 
    LEVEL_HEADRM=4 # Equiv of Admin
    LEVEL_NOACCESS=-1

def accessLevelToString(x,blanks=[]):
	if x in blanks: return ""
	if x==AccessByMember.LEVEL_NOACCESS: return "NoAccess"
	try:
		return AccessByMember.ACCESS_LEVEL[x]
	except:
		return "??"
    
# Define roles
class Role(db.Model):
    __tablename__ = 'roles'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(50), unique=True)

# Define User to Role Mapping
class UserRoles(db.Model):
    __tablename__ = 'userroles'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id', ondelete='CASCADE'))
    role_id = db.Column(db.Integer(), db.ForeignKey('roles.id', ondelete='CASCADE'))

class Resource(db.Model):
    __tablename__ = 'resources'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(50), unique=True)
    short = db.Column(db.String(20), unique=True,nullable=True)
    description = db.Column(db.String(50))
    owneremail = db.Column(db.String(50))
    last_updated = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
    slack_chan = db.Column(db.String(50))
    slack_admin_chan = db.Column(db.String(50))
    info_url = db.Column(db.String(150))
    info_text = db.Column(db.String(150))
    slack_info_text = db.Column(db.String())

class ResourceAlias(db.Model):
    __tablename__ = 'resourcealiases'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    alias = db.Column(db.String(50), unique=True)
    resource_id = db.Column(db.Integer(), db.ForeignKey('resources.id', ondelete='CASCADE'))



class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    paysystem = db.Column(db.String(50))
    subid = db.Column(db.String(50),nullable=False)
    customerid = db.Column(db.String(50),nullable=False)
    name = db.Column(db.String(50))
    email = db.Column(db.String(50))
    # NOTE CHANGE FROM PLANNAME" to PLAN
    plan = db.Column(db.String(50))
    expires_date = db.Column(db.DateTime())
    created_date = db.Column(db.DateTime())
    updated_date = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
    checked_date = db.Column(db.DateTime())
    active = db.Column(db.Integer())
    membership = db.Column(db.String(50),nullable=False,unique=True)
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id'))

# membership is a unique identifier for each member. Each member SHOULD have one.
# (If they don't, they have a problem or inactive membership)
# It might look something like:
# stripe:user@example.com:first:last

# Waiver Data
class Waiver(db.Model):
    __tablename__ = 'waivers'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    waiver_id = db.Column(db.String(50))
    firstname = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    email = db.Column(db.String(50))
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id'))
    created_date = db.Column(db.DateTime())

# RFID data
class MemberTag(db.Model):
    # TODO: Handle change from tagsbymember
    __tablename__ = 'tags_by_member'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    #tag_id = db.Column(db.String(50)) "old" hashed data
    tag_ident = db.Column(db.String(50))  # "new" 10-digit,zero paded, raw,  unhashed data
    tag_type = db.Column(db.String(50))
    tag_name = db.Column(db.String(50))
    updated_date = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
    member = db.Column(db.String(50))
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id', ondelete='CASCADE'))

    @property
    def longhash(self):
        try:
            m = hashlib.sha224()
            rfidStr = "%.10d"%(int(self.tag_ident))
            m.update(str(rfidStr).encode())
            return str(m.hexdigest())
        except:
            return None
        
    @property
    def shorthash(self):
        try:
            return self.longhash[0:4]+"..."+self.longhash[-4:]
        except:
            return None

    # member_id MIGHT not exist if user is gone, but "member" should be ok

class Blacklist(db.Model):
    # TODO: Handle change from tagsbymember
    __tablename__ = 'blacklist'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    entry = db.Column(db.String(50))
    entrytype = db.Column(db.String(50))
    reason = db.Column(db.String(50))
    updated_date = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())

# Physical RATT - One "node" may support multiple "tools" someday
class Node(db.Model):
    # TODO: Handle change from tagsbymember
    __tablename__ = 'nodes'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(20))
    mac = db.Column(db.String(20))

# A node can have multiple KV entries for config
class NodeConfig(db.Model):
    # TODO: Handle change from tagsbymember
    __tablename__ = 'nodeconfig'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    value = db.Column(db.String(50))
    node_id = db.Column(db.Integer(), db.ForeignKey('nodes.id', ondelete='CASCADE'))
    key_id = db.Column(db.Integer(), db.ForeignKey('kvopts.id', ondelete='CASCADE'))

class KVopt(db.Model):
    # TODO: Handle change from tagsbymember
    __tablename__ = 'kvopts'
    __bind_key__ = 'main'
    id = db.Column(db.Integer(), primary_key=True)
    keyname = db.Column(db.String(50))
    default = db.Column(db.String(50))
    kind = db.Column(db.String(50),default="string")
    options = db.Column(db.String())
    description = db.Column(db.String(100))
    displayOrder = db.Column(db.Integer, default=100)

    valid_kinds=['string','integer','boolean']
##
## LOGS
##
## Separate databse / binding
##

class Logs(db.Model):
    __tablename__ = 'log'
    __bind_key__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id', ondelete='CASCADE'))
    node_id = db.Column(db.Integer(), db.ForeignKey('nodes.id', ondelete='CASCADE'))
    tool_id = db.Column(db.Integer(), db.ForeignKey('tools.id', ondelete='CASCADE'))
    resource_id = db.Column(db.Integer(), db.ForeignKey('resources.id', ondelete='CASCADE'))
    message = db.Column(db.String(100))
    doneby = db.Column(db.Integer(), db.ForeignKey('members.id', ondelete='CASCADE'))
    time_logged = db.Column(db.DateTime(timezone=True), server_default=db.func.now(),index=True)
    time_reported = db.Column(db.DateTime(timezone=True), server_default=db.func.now(),index=True)
    event_type = db.Column(db.Integer(),index=True)
    event_subtype = db.Column(db.Integer(),index=True)

class UsageLog(db.Model):
    __tablename__ = 'usagelog'
    __bind_key__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id', ondelete='CASCADE'))
    tool_id = db.Column(db.Integer(), db.ForeignKey('tools.id', ondelete='CASCADE'))
    resource_id = db.Column(db.Integer(), db.ForeignKey('resources.id', ondelete='CASCADE'))
    time_logged = db.Column(db.DateTime(timezone=True), server_default=db.func.now(),index=True)
    time_reported = db.Column(db.DateTime(timezone=True))
    idleSecs = db.Column(db.Integer())
    activeSecs = db.Column(db.Integer())
    enabledSecs = db.Column(db.Integer())

# TODO I'm pretty sure this class isn't used at all (???)
class OAuth(OAuthConsumerMixin, db.Model):
    __tablename__ = 'oauth'
    __bind_key__ = 'main'
    user_id = db.Column(db.Integer, db.ForeignKey(Member.id))
    user = db.relationship(Member)
    pass
