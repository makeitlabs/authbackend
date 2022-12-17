# authbackend

Some rough documentation as of April, 2022

# Running via. Docker/Container Images

To run or build Docker, Containers or Kubernentes, see the `Dockerfile`

To Build:
`sudo docker build -t authbackend .`

To run flask debugger:
`sudo docker run --rm -it  --entrypoint /bin/bash authbackend`

To run w/ gunicorn proxy (and a proxy path):
`docker run -it  -p 5000:5000   --env AUTHIT_PROXY_PATH=authit authbackend`

You probably want to create an external persistant volume to hold `makeit.ini` and log/db files.

`AUTHIT_INI` environmental variable should be set to a path of `makeit.ini` (external volume)
note that the `makeit.ini` file must also contain proper paths to database and log files!

As of this writing - it doesn't do anything to properly setup database or `makeit.ini` files
(I think it will run a developer-staging setup as-is). This means you need to restore and load
databases and `makeit.ini` from backups to work in production

Add a persistant volume to docker like:
`docker run --rm -it -v authitdata_devel:/opt/authit`

Set up a Persistant Volume like:
`docker volume create authitdata_devel`

Then inspect persitant volume to find out where it's path is on your filesystem. Place the `makeit.ini`, `db` and `logdb` files in the persistent volume

Modify the `makeit.ini` file to point to the aforemented databases. Note that the Persitant Volume will mount to `/opt/makeit` - so make sure that is the "root" of the path you use - i.e. `/opt/makeit/db.sq3`

Run as below. Note that you will need to specify:
- Port mapping (Gnuicorn and Flask will run as port 5000) - map this to outside the docker
- You need to specify a `AUTHIT_PROXY_PATH` if you want to run behind a proxy. This shall be the base path part of the URL. For example, if you wan to run as `http://makeit.com/staging` - then the `AUTHIT_PROXY_PATH` must be `staging`. If you do NOT specify an `AUTHIT_PROXY_PATH`, it will run with Flask debugger (instead of Gunicorn - i.e. you cannot proxy) and you will have to just connect to it with the raw port, above.
- The `AUTHIT_INI` environmental varabile has to be set to the path inside the docker for the `makeit.ini` file.

If you don't know where to get the database(s) from - use the "restore.py" script with the S3 keys in the `makeit.ini` file to download old backups of them from AWS.

Debug  example:
`docker run --rm -it -p 5000:5000 -v authit-devel:/opt/makeit --env=AUTHIT_PROXY_PATH=dev --env=AUTHIT_INI=/opt/makeit/makeit.ini  --entrypoint /bin/bash authbackend`
This would run as http://node:5000/dev

Runtime example:
`docker run --rm -it -p 5000:5000 -v authit-devel:/opt/makeit --env=AUTHIT_PROXY_PATH=dev --env=AUTHIT_INI=/opt/makeit/makeit.ini  authbackend`


# Non-containerized stuff

## Install prerequisites

See `versions.txt` for known-good package versions

(As of Ubuntu 20.04.1) Start with only doing the stuff that you NEED to below, and only if you have problems, try depricated or questionable stuff.

See pip3.freeze for reference of working config

(DEPRICATE??) `sudo apt install libcurl4-openssl-dev libssl-dev`

(DEPRICATE??) `sudo apt install sqlite3 flask python-pycurl python-httplib2 python-auth2client`

`sudo apt install sqlite3 python3-pip python3-pycurl mosquitto net-tools`

```
pip3 install --upgrade cryptography
pip3 install testresources
pip3 install flask_login
pip3 install flask_user
pip3 install flask_dance
pip3 install stripe
pip3 install apiclient
pip3 install google-api-python-client
pip3 install paho-mqtt
pip3 install pytz
pip3 install boto3
pip3 install oauth2client
pip3 install google-oauth
pip3 install sqlalchemy_utils
pip3 install email_validator
sudo apt install libcurl4-openssl-dev libssl-dev # Often needed for pycurl below
pip3 install pycurl
pip3 install configparser
pip3 install functools (Unclear if this actually works or not??)
pip3 install slackclient (OLD - SHOULDN'T NEED)
pip3 install slack_sdk 
pip3 install icalendar
pip3 install coverage (If test coverage is used)
```

For Covid-19 video kiosk compliance reporting script
`sudo apt install ffmpeg`

## Quick setup

Copy `makeit.ini` from your existing system. Thiss will DIFFER in production vs staging systems!

Fetch databases from old system - or restore nightly backups like:

```
./restore.py 2021-02-10-db.sq3
./restore.py 2021-02-10-logdb.sq3
```
...and change filenames to something to run with...
```
mv 2021-02-10-db.sq3 db.sq3
mv 2021-02-10-logdb.sq3 dblog.sq3
```
Make sure these two databases match the `Database` and `LogDatabase` entries in `makeit.ini`
(If you don't have a makeit.ini - you will not have required keys to fetch backups)

If database is sufficiently new (i.e. subscriptions were all up-to-date) everything should be ready to go. But if you need to do anything else, like you are running a development server and won't be able to immediatley use OATH (need local login users), or you can't login because the database was old and it thinks your account is expired and you need to manual update subscrptions - read onward.

## Creating stub database

(ONLY do this if you are starting from a completely clean slate and importing/migrating no old data!)
`sqlite3 makeit.db < schema.sql`

## Set up .ini file

(ONLY do this if you are starting from a completely clean slate andhave no existing `makeit.ini`)
`cp makeit.ini.example makeit.ini`

You might want to edit some things in the file before running the server. 

Make sure that if you are running a TEST server, that you set "Deployment:" 
to something other thatn "Production"

## Setup Database

(This deals mostly with importing a 2018-vintage DB - or starting from a totally clean slate!)

The database is normally the makeit.db. You will probably need to copy this over from somewhere (i.e. live server).
If you don't have a "live" one to grab and use, you can create an example one with:

`./migrate_db.py --overwrite makeit.db --testdata --nomigrate`

This utility can also be used to migrate a database to a "new" schema - but this obviously will change drastically from
time-to-time, depending on which versions you are migrating to and form. The "--testdata" and "--testonly" flags won't
actually do any data migration, but will just give you a blank database with some test data in it.

You can also start with a VERY minimal database with:

`python authserver.py --createdb`

## Full data migration

Again, this is dependent on you having some extra data files for 
old database, etc - and will vary from versons - but generaly:

(First line here is to migrate a pre-2018 database, the second two CAN be used to force a payment update on migrated data. This is generally unnecessary, but sometimes helpful if you migrate and then get locked-out because data is so old your account has expired!)

```
./migrate_db.py --overwrite makeit.db
python authserver.py --command updatepayments
python authserver.py --command memberpaysync --test
```

After you migrate - you may want to manually run the nightly cron job
to synchronize payment and waiver data by doing:

`curl http://testkey:testkey@localhost:5000/api/cron/nightly`

## More test stuff

(NOTE: This populates with FAKE DATA. Don't do if you're migrating)
You can also optionally add fake usage data for the test resource
by running:

`./popusagedata.py`

This will add a week's worth of data - add more like:

`./popusagedata.py --days=30`

If you have added the `--testdata` flag to the migrate, you can run
a quick regression/sanity check with:

`test/bigtest.py`

## OAuth Stuff

(This is mostly for running local test-servers)

On the machine(s) you are connecting to a test deployment with,
add the following line to your /etc/hosts:

`x.x.x.x rattdev.com`

(x.x.x.x being the IP address of the test backend server)

When running locally - use http://rattdev.com:5000 as the URL you are connecting to.
This is because the OAuth login is configured to allow this as a valid URL.

If you don't do this - you will get an error on OAuth login saying there is a 
redirect URL mismatch.


## Running development server

In a non-production enviroment, allow non-SSL OAuth with:

`export OAUTHLIB_INSECURE_TRANSPORT=1`

`python authserver.py`

This should start a server on `0.0.0.0:5000` which you can get to via browser or use the API calls.  The default user/password is admin/admin (configured in .ini file) - but this won't be present if you're using a production database.

There are a few things you generally want to do in a local debug environment:

* In `makeit.ini` set `Deployment:` to something other than `Production` (This will make your GUI look different than production)
* In `makeit.ini` set `Logins: all`
* In `makeit.ini` set `DefaultLogin:` to `local`. THis will let you login with local credentials when `oauth` isn't working
* Do `python authserver.py --command addadmin admin admin` to add an admin account w/ password Admin (if there isn't one - like from a live database)
* Add `local.makeitlabs.com` to your `/etc/hosts` to resolve to localhost. Use that address (in we browser) to access the server. This name is whitelisted in the Oauth rules, so Oauth will be able to redirect to it (i.e. your local server)

## Fix for newer versions of Flask library

(Unclear if needed for Python3/Ubunto20+ vintage)

If you get a similar error to:
```
Traceback (most recent call last):
  File "authserver.py", line 24, in <module>
    from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
ImportError: No module named ext.login
```

...you might have newer versions of the Flask library which have a different import syntax.

Change the import line in `authserver.py` to:
```python
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
```

## Using the CLI: 

CLI is needed for some zero-start conditions - like assigning privilieges, or (non-oauth-login) passwords
before any admins or access is set up on the system.

Some important commands are:

`python authserver.py --command passwd Member.Name  myPassword`
Adds a password to an account for non-oauth access.

`python authserver.py --command grant Member.Name Admin`
Give member admin privileges


There are lots more - for info do:

`python ./authserver.py --command help`

## Other Housekeeping

There are several scripts that need to be added as cron jobs to do things like:

* Snapshot the database
* Handle payment and waiver updates
* Get snapshots of ACL lists - send messages to slack groups of changes since prior run
* Back all snaps up to Amazon
* Node monitoring
* Covosk Compliance

For an example crontab - see `crontab.txt`

# Backups

Backups should be run with `nightly.py` script in cron file
To help restore backups - you can use the `restore.py` helper script


# Updating to latest version

##  Multitrain/Python3 Update

Add `MemberFoldersPath` to `[General]` section of `makeit.ini` with mount point to Member Folders
Add `autoplot` section to `makeit.ini`
`sudo pip install icalendar`

## Log DB

```
CREATE TABLE vendinglog (
	id INTEGER NOT NULL, 
	member_id INTEGER NOT NULL, 
	invoice VARCHAR(100), 
	product VARCHAR(100), 
	comment VARCHAR(100), 
	doneby INTEGER, 
  oldBalance INTEGER,
  addAmount INTEGER,
  purchaseAmount INTEGER,
  surcharge INTEGER,
  totalCharge INTEGER,
  newBalance INTEGER,
	time_logged DATETIME DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE, 
	FOREIGN KEY(doneby) REFERENCES members (id) ON DELETE CASCADE
);
```

## Main DB

# HOTFIX - member balances

```
ALTER TABLE members ADD COLUMN balance INTEGER;
```

# v1.0.7 Update

```
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

CREATE TABLE training (
        id INTEGER NOT NULL,
        name VARCHAR(150),
        hours INTEGER,
        permit INTEGER,
        days INTEGER,
        url VARCHAR(150),
        required INTEGER,
        required_endorsements VARCHAR(50),
        endorsements VARCHAR(50),
        resource_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(required) REFERENCES resources (id) ON DELETE CASCADE,
        FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);

INSERT INTO training(id,hours,permit,days,url,required,resource_id) SELECT id,sa_hours,sa_permit,sa_days,sa_url,sa_required,id FROM resources WHERE (sa_url is not null and sa_url != "");

CREATE TABLE resources2 (
        id INTEGER NOT NULL,
        name VARCHAR(50),
        short VARCHAR(20),
        description VARCHAR(50),
        owneremail VARCHAR(50),
        last_updated DATETIME,
        slack_chan VARCHAR(50),
        slack_admin_chan VARCHAR(50),
        info_url VARCHAR(150),
        info_text VARCHAR(150),
        slack_info_text VARCHAR, 
        age_restrict INTEGER, 
        permissions VARCHAR(255), 
        PRIMARY KEY(id), 
        UNIQUE (name),
        UNIQUE (short)
);

INSERT INTO resources2 (
        id,
        name,
        short,
        description,
        owneremail,
        last_updated,
        slack_chan,
        slack_admin_chan,
        info_url,
        info_text,
        slack_info_text, 
        age_restrict, 
        permissions
        )
        SELECT 
          id,
          name,
          short,
          description,
          owneremail,
          last_updated,
          slack_chan,
          slack_admin_chan,
          info_url,
          info_text,
          slack_info_text, 
          age_restrict, 
          permissions 
        FROM resources;

DROP TABLE resources;
ALTER TABLE resources2 RENAME TO resources;

CREATE TABLE quizquestion (
        id INTEGER NOT NULL,
        question TEXT,
        answer TEXT,
        idx INTEGER,
        training_id INTEGER NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(training_id) REFERENCES training (id) ON DELETE CASCADE
);
INSERT INTO quizquestion (
        id,
        question,
        answer,
        idx,
        training_id)
        SELECT 
          id,
          question,
          answer,
          idx,
          resource_id
        FROM resourcequiz;
DROP TABLE resourcequiz;

CREATE TABLE tempauth (
        id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        admin_id INTEGER NOT NULL,
        resource_id INTEGER NOT NULL,
        expires DATETIME,
        timesallowed INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE,
        FOREIGN KEY(admin_id) REFERENCES members (id) ON DELETE CASCADE,
        FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);

ALTER TABLE members ADD COLUMN memberFolder VARCHAR(255);
insert into roles (id,name) values (7,"LeaseMgr");
ALTER TABLE members ADD COLUMN balance INTEGER DEFAULT 0;

COMMIT;
PRAGMA foreign_keys=on;
###  delete from  subscriptions where member_id = 412; (Delete only one SUB for him!!)
```

## v1.0.8 Update
```
sqlite3 <<dbfile>>
ALTER TABLE resources ADD COLUMN sa_required_endorsements VARCHAR(50);
ALTER TABLE resources ADD COLUMN sa_endorsements VARCHAR(50);
```

*** BUT ALSO: Check and delete duplicate Subscription Records!!

### Fix wsgl config

Verify that `authserver.wsgi` is set for your appopriate deploy! (See `authserver.wsgi.EXAMPLE` for example)

In `makeit.ini` set a defualt door lockout message with `LockoutMessage` in the `General` section. This should not be present for normal deployments, but might want to say `Covid-19 Training Required` if appropriate.

# Slack

Get Slack working - make sure the credentails below are set up in `makeit.ini` and run `./slacktest.py`. It should *PASS*!
If not - you probably have permissions/scope problems, below.


Slack permissions changed - so you might want to go into slack API and regenerate permissions for the API user. You need to have bunch of new permisions to allow training bot to add people to channels, including:

`channels:manage` and `channels:write` 

...But these scopes don't seem to be directly listed - but there are abunch of others that you seem to need, possibly including:

Bot token scopes:
```
calls:read calls:write channels:join channels:manage channels:read chat:write dnd:read files:read groups:read
groups:write im:history im:read im:write incoming-webhook mpim:history mpim:read mpim:write pins:write reactions:read
reactions:write remote_files:read remote_files:share remote_files:write team:read users:read users:read.email users:write```

User token scopes:
``` channels:write ``

Add the following OAuth scopes:
`identify,bot,channels:read,groups:read,im:read,mpim:read,chat:write:bot,channels:write,rtm:stream`

This should ALREADY be done - just set the ADMIN_API_TOKEN to the "Authorizaiton Bot" and run Slacktest below.

It's a bit of a freakin mystery - the good news is that if you run

`./slacktest.py`

.... it will tell you at the very end if there were errors in the permissions, and what permissins it was lacking.

You can add API stuff here: https://api.slack.com/apps
* Click your app
* "Features and Functionality"
* "Permissions"

# Slack Setup - there are two tokens you need:
`BOT_API_TOKEN` - This is the one above which requires all the "granular scopes" to do stuff. It is used most often to send messages to channels, from the MQTT Daemon, and other stuff in the backend. the `slacktest.py` mostly uses this. Go to "OAuth & Permissions" and use the "Bot User OAuth Access Token" provided.

`ADMIN_API_TOKEN` - This is used by the slackdaemon `toolauthslack` for the Tool Authorization Slack robot. This uses an "RTM" connection in Slack. This means it must be created as a "Classic App" - i.e. it cannot have "granular scopes". I think it only needs a "bot" scope. *Do Not* let Slack trick you into converting this into a "new style" app with Granular Scopes or it will not work! If "RTM Connect" fails - it means this token is not correct. Once you create a classic app - go to "OAuth Tokens" and use the "Bot User OAuth Access Token" from this.

`ADMIN_API_TOKEN` seems to need the following scopes:
`bot`
`chat:write:bot`
`incoming-webhook`
`channels:read`
`groups:read`
`mpim:read`
`channels:write`

# systemctl setup
We generally use systemctl to create services to make sure these two are always running:
```
             ├─authbackend-slack.service
             │ └─/usr/bin/python /var/www/authbackend-ng/toolauthslack.py
             └─authbackend-mqtt.service
               └─/usr/bin/python /var/www/authbackend-ng/mqtt_daemon.py
```


# 1.0.7 Migration

`ALTER TABLE resources ADD COLUMN permissions VARCHAR(255);`
