#!/bin/bash

ln -s /bin/bash /usr/bin/bash


set -x 1
set -e 1

PORT=5000
if [[ ! -z "${AUTHIT}" ]]; then
PORT=${AUTHIT_PROXY_PORT}
fi 

if [[ ! -z "${AUTHIT_DEBUGWAIT}" ]]; then
  echo In Debug wait
  sleep infinity
elif [[ ! -z "${AUTHIT_PROXY_PATH}" ]]; then
  echo Running gunicorn proxy path $AUTHIT_PROXY_PATH port $PORT
  SCRIPT_NAME=/${AUTHIT_PROXY_PATH}  gunicorn -w 4 -b 0.0.0.0:${PORT}  authserver:app
else
  ./run.sh
fi
