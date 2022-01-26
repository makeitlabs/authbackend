#!/bin/bash
FLASK_DEBUG=1 FLASK_APP=authserver.py FLASK_ENV=development flask run --port 5000 --host 0.0.0.0 --with-threads
