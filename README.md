# authbackend

Some rough documentation as of December 2018.

## Install prerequisites

(Note: Ubuntu-flavored)

`sudo apt install sqlite3 flask python-pycurl python-httplib2 python-auth2client`

`pip install flask-login`
`pip install stripe`
`pip install apiclient`
`pip install --upgrade google-api-python-client`

## Creating stub database

`sqlite3 makeit.db < schema.sql`

## Set up .ini file

`cp makeit.ini.example makeit.ini`

You might want to edit some things in the file before running the server.

## Running development server

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

