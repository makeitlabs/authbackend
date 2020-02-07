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

This should start a server on `0.0.0.0:5000` which you can get to via browser or use the API calls.  The default user/password is admin/admin (configured in .ini file).

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


# v0.8 Migration

You will need to apply the following DB schema changes *manually* when migrating from v0.7 to v0.8

```BEGIN TRANSACTION;
CREATE TABLE maintsched (
        id INTEGER NOT NULL,
        name VARCHAR(50),
        "desc" VARCHAR(100),
        realtime_span INTEGER,
        realtime_unit VARCHAR(12),
        machinetime_span INTEGER,
        machinetime_unit VARCHAR(12),
        resource_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);
ALTER TABLE nodes ADD last_ping datetime;
ALTER TABLE tools ADD displayname VARCHAR(50);
ALTER TABLE members ADD COLUMN dob DATETIME;
ALTER TABLE resources ADD COLUMN age_restrict INTEGER;
ALTER TABLE apikeys ADD COLUMN acl VARCHAR(255);

CREATE TABLE prostorelocations (
	location VARCHAR(50) NOT NULL, 
	id INTEGER NOT NULL, 
	loctype INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (location)
);

CREATE TABLE prostorebins (
	id INTEGER NOT NULL, 
	member_id INTEGER, 
	name VARCHAR(20), 
	status INTEGER NOT NULL, 
	location_id INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (name),
	FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE, 
	FOREIGN KEY(location_id) REFERENCES prostorelocations (id) ON DELETE CASCADE
);
ALTER TABLE waivers ADD waivertype Integer;
insert into roles ('name')  values ('ProStore');
COMMIT;
```

You will also need to update waiver data to include [new] waiver-types before going live:

`python authserver.py --command fixwaivers`

Get a jumpstart on entering pro-storage stuff with:

`python authserver.py --command prostore_migrate`
