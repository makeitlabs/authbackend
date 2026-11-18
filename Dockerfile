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
RUN apt-get install -y libssl-dev libcurl4-openssl-dev python3-dev gcc ssh curl sqlite3 bash vim-tiny awscli redis

RUN dpkg -l > versions.txt

FROM authpackages as flaskbase

COPY requirements.txt .
RUN cat  requirements.txt
RUN pip3 install -r requirements.txt
RUN pip3 freeze > requirements.txt.installed

FROM flaskbase 

COPY . . 

ENTRYPOINT ["/bin/bash"]

CMD [ "dockerentry.sh" ]
