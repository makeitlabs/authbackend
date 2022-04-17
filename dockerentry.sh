#!/bin/bash

ln -s /bin/bash /usr/bin/bash


set -x 1
set -e 1

PORT=5000
if [[ ! -z "${AUTHIT}" ]]; then
PORT=${AUTHIT_PROXY_PORT}
fi 

MAKEITINI=/opt/authit/makeit.ini
if [[ ! -z "${AUTHIT_INI}" ]]; then
MAKEITINI=${AUTHIT_INI}
else
declare -x MAKEIT_INI=$MAKETINI
fi 

echo AUTHIT_INI set to $MAKEITINI

if [ ! -f $MAKEITINI ]; then
    echo $MAKEITINI does not exist!
    echo Set AUTHIT_DEBUGWAIT to spin up an exec shell
    exit 1
fi

if [[ ! -z "${AUTHIT_DEBUGWAIT}" ]]; then
  echo In Debug wait
  /bin/bash
elif [[ ! -z "${AUTHIT_PROXY_PATH}" ]]; then
  echo Running gunicorn proxy path $AUTHIT_PROXY_PATH port $PORT
  SCRIPT_NAME=/${AUTHIT_PROXY_PATH}  gunicorn -w 4 -b 0.0.0.0:${PORT}  authserver:app
else
  ./run.sh
fi
