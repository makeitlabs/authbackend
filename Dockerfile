# sudo docker build -t authbackend .

# Create the data volume first!
# sudo docker volume create authitdata_devel

# To run flask debugger
# sudo docker run --rm -it -v authitdata_devel:/opt/authit/ --entrypoint /bin/bash authbackend

# To run w/ gunicorn proxy (and a proxy path)
# docker run -it  -p 5000:5000 -v authitdata_devel:/opt/authit/  --env AUTHIT_PROXY_PATH=authit authbackend
# Set AUTHIT_INI to makeit.ini path

# Add persistatnt volume like:
# sudo docker run --rm -it -v authitdata_devel:/opt/authit  
# docker run --rm -it -v authit-devel:/opt/makeit --env=AUTHIT_INI=/opt/makeit/makeit.ini  --entrypoint /bin/bash authbackend


# Run
# docker run --rm -it -p 5000:5000 -v authit-devel:/opt/makeit --env=AUTHIT_PROXY_PATH=dev                  --env=AUTHIT_INI=/opt/makeit/makeit.ini  authbackend



FROM python:3.8-slim-buster as authpackages
MAINTAINER Brad Goodman "brad@bradgoodman.com"
WORKDIR /authserver

RUN apt-get update
RUN apt-get install -y libssl-dev libcurl4-openssl-dev python3-dev gcc ssh curl sqlite3 bash vim-tiny awscli

RUN dpkg -l > versions.txt

FROM authpackages as flaskbase


#RUN pip3 install flask
#RUN pip3 install slack_sdk 
#RUN pip3 install --upgrade cryptography
#RUN pip3 install testresources
#RUN pip3 install flask_login
#RUN pip3 install flask_user
#RUN pip3 install flask_dance
#RUN pip3 install stripe
#RUN pip3 install apiclient
#RUN pip3 install google-api-python-client
#RUN pip3 install paho-mqtt
#RUN pip3 install pytz
#RUN pip3 install boto3
#RUN pip3 install oauth2client
#RUN pip3 install google-oauth
#RUN pip3 install sqlalchemy_utils
#RUN pip3 install email_validator
#RUN pip3 install configparser
#RUN pip3 install gunicorn
#RUN pip3 install pycurl
#RUN pip3 install icalendar

# We dont need
#RUN pip3 install functools 
#RUN pip3 install slackclient (OLD - SHOULDN'T NEED)

COPY requirements.txt .
RUN cat  requirements.txt
RUN pip3 install -r requirements.txt
RUN pip3 freeze > requirements.txt.installed


FROM flaskbase 

COPY . . 

ENTRYPOINT ["/bin/bash"]

CMD [ "dockerentry.sh" ]
