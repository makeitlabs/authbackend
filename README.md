# authbackend

Some rough documentation as of December 2018.

## Install prerequisites

(Note: Ubuntu-flavored)

`sudo apt install libcurl4-openssl-dev libssl-dev`
`sudo apt install sqlite3 flask python-pycurl python-httplib2 python-auth2client`

`pip install flask-login`
`pip install flask-user`
`pip install flask-dance`
`pip install stripe`
`pip install apiclient`
`pip install --upgrade google-api-python-client`
`pip install paho-mqtt`
`pip install pytz`
`pip install boto3`
`pip install --upgrade oauth2client`
`pip install google-oauth`
`sudo pip install sqlalchemy_utils`

For Covid-19 video kiosk compliance reporting script
`sudo apt install ffmpeg`

## Creating stub database

`sqlite3 makeit.db < schema.sql`

## Set up .ini file

`cp makeit.ini.example makeit.ini`

You might want to edit some things in the file before running the server. 

Make sure that if you are running a TEST server, that you set "Deployment:" 
to something other thatn "Production"

## Setup Database

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

```
./migrate_db.py --overwrite makeit.db
python authserver.py --command updatepayments
python authserver.py --command memberpaysync --test
```

After you migrate - you may want to manually run the nightly cron job
to synchronize payment and waiver data by doing:

`curl http://testkey:testkey@localhost:5000/api/cron/nightly`

## More test stuff

You can also optionally add fake usage data for the test resource
by running:

`./popusagedata.py`

This will add a week's worth of data - add more like:

`./popusagedata.py --days=30`

If you have added the `--testdata` flag to the migrate, you can run
a quick regression/sanity check with:

`test/bigtest.py`

## OAuth Stuff

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

You will want to run `nightly.py` on some nightly cron job. It will:

* Snapshot the database
* Handle payment and waiver updates
* Get snapshots of ACL lists - send messages to slack groups of changes since prior run
* Back all snaps up to Amazon

To help restore backups - you can use the `restore.py` helper script

For an example crontab - see `crontab.txt`


# Update/Deploy

#  Multitrain Update
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

INSERT INTO training(hours,permit,days,url,required,resource_id) SELECT sa_hours,sa_permit,sa_days,sa_url,sa_required,id FROM resources WHERE (sa_url is not null and sa_url != "");

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
        endorsements VARCHAR(50), 
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
        permissions, 
        endorsements)
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
          permissions, 
          endorsements
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

COMMIT;
PRAGMA foreign_keys=on;
```

# v1.0.8 Update
```
sqlite3 <<dbfile>>
ALTER TABLE resources ADD COLUMN sa_required_endorsements VARCHAR(50);
ALTER TABLE resources ADD COLUMN sa_endorsements VARCHAR(50);
```

### Fix wsgl config

Verify that `authserver.wsgi` is set for your appopriate deploy! (See `authserver.wsgi.EXAMPLE` for example)

In `makeit.ini` set a defualt door lockout message with `LockoutMessage` in the `General` section. This should not be present for normal deployments, but might want to say `Covid-19 Training Required` if appropriate.


### If you care about getting Slack training invites working:

Slack permissions changed - so you might want to go into slack API and regenerate permissions for the API user. You need to have bunch of new permisions to allow training bot to add people to channels, including:

`channels:manage` and `channels:write` 

...But these scopes don't seem to be directly listed - but there are abunch of others that you seem to need, possibly including:

Bot token scopes:
```
calls:read calls:write channels:join channels:manage channels:read chat:write dnd:read files:read groups:read
groups:write im:history im:read im:write incoming-webhook mpim:history mpim:read mpim:write pins:write reactions:read
reactions:write remote_files:read remote_files:share remote_files:write team:read users:read users:read.email users:write```

User token scopes:
``` channels:write ```

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
