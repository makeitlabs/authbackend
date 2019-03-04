#!/usr/bin/env python
# vim:tabstop=2:expandtab:shiftwidth=2
# Utilities for MakeIt Labs



from json import dumps as json_dumps
import argparse,sys
import paho.mqtt.publish as mqtt_pub
import ConfigParser

def send_message(topic,data,mqtt_opts):
    try:
      mqtt_pub.single(topic, data, **mqtt_opts)
    except BaseException as e:
        logging.warning("MQTT acl/update failed to send tool open message: "+str(e))

def send_lock(node,reason,base_topic,mqtt_ops):
  topic= base_topic+"/control/node/%s/personality/lock" % (node)
  data = json_dumps({'reason':reason})
  send_message(topic,data,mqtt_opts)

def send_unlock(node,tool,base_topic,mqtt_ops):
  topic= base_topic+"/control/node/%s/personality/unlock" % (node)
  data = json_dumps({'tool':tool})
  send_message(topic,data,mqtt_opts)

def send_status(node,subtopic,data,base_topic,mqtt_ops):
  topic= base_topic+"/status/node/%s/%s" % (node,subtopic)
  send_message(topic,data,mqtt_opts)

def send_login(node,member,allowed,base_topic,mqtt_opts):
  topic= base_topic+"/status/node/%s/personality/login" % (node)
  data=json_dumps({"member":member,"allowed":allowed})
  send_message(topic,data,mqtt_opts)

def send_logout(node,member,base_topic,mqtt_opts):
  topic= base_topic+"/status/node/%s/personality/logout" % (node)
  data=json_dumps({"member":member,"activeSecs": 2, "enabledSecs": 5,"idleSecs": 3, "reason": "timeout"})
  send_message(topic,data,mqtt_opts)

def send_activity(node,member,base_topic,mqtt_opts):
  topic= base_topic+"/status/node/%s/personality/activity" % (node)
  data=json_dumps({"member":member,"active":True})
  send_message(topic,data,mqtt_opts)

def send_inactivity(node,member,base_topic,mqtt_opts):
  topic= base_topic+"/status/node/%s/personality/activity" % (node)
  data=json_dumps({"member":member,"active":False})
  send_message(topic,data,mqtt_opts)

def send_poweron(node,base_topic,mqtt_opts):
  topic= base_topic+"/status/node/%s/system/power" % (node)
  data=json_dumps({"state":"restored"})
  send_message(topic,data,mqtt_opts)

def send_poweroff(node,base_topic,mqtt_opts):
  topic= base_topic+"/status/node/%s/system/power" % (node)
  data=json_dumps({"state":"shutdown"})
  send_message(topic,data,mqtt_opts)

def send_issue(node,member,issue,base_topic,mqtt_opts):
  topic= base_topic+"/status/node/%s/system/issue" % (node)
  data=json_dumps({"member":member,"issue":issue})
  send_message(topic,data,mqtt_opts)

def get_mqtt_config():
  Config = ConfigParser.ConfigParser({})
  Config.read('makeit.ini')
  mqtt_opts={}
  mqtt_base_topic = Config.get("MQTT","BaseTopic")
  mqtt_opts['hostname'] = Config.get("MQTT","BrokerHost")
  mqtt_opts['port'] = Config.getint("MQTT","BrokerPort")
  if Config.has_option("MQTT","keepalive"):
      mqtt_opts['keepalive']=Config.getint("MQTT","keepalive")
  if Config.has_option("MQTT","SSL") and Config.getboolean("MQTT","SSL"):
      mqtt_opts['tls']={}
      mqtt_opts['tls']['ca_certs'] = Config.get('MQTT_SSL', 'ca_certs')
      mqtt_opts['tls']['certfile'] = Config.get('MQTT_SSL', 'certfile')
      mqtt_opts['tls']['keyfile'] = Config.get('MQTT_SSL', 'keyfile')

      if Config.has_option('MQTT_SSL', 'tls_version'):
          mqtt_opts['tls']['tls_version'] = Config.get('MQTT_SSL', 'tls_version')

      if Config.has_option('MQTT_SSL', 'ciphers'):
          mqtt_opts['tls']['ciphers'] = Config.get('MQTT_SSL', 'ciphers')

  if Config.has_option("MQTT","username"):
      mqtt_opts['auth']={'username':app.globalConfig.Config.get("MQTT","username"),'password':app.globalConfig.Config.get("MQTT","password")}
  return (mqtt_base_topic,mqtt_opts)

if __name__ == "__main__":
  parser=argparse.ArgumentParser()
  parser.add_argument("--command",help="Special command",action="store_true")
  (args,extras) = parser.parse_known_args(sys.argv[1:])
	(base_topic,mqtt_opts) = get_mqtt_config()
	print mqtt_opts,base_topic

  test_node = '001122334455'
  test_tool = 'TestTool'
  test_user = 'testuser'
  send_poweron(test_node,base_topic,mqtt_opts)
  send_lock(test_node,"Test Lock",base_topic,mqtt_opts)
  send_unlock(test_node,test_tool,base_topic,mqtt_opts)
  send_login(test_node,'noprivs',False,base_topic,mqtt_opts)
  send_login(test_node,test_user,True,base_topic,mqtt_opts)
  send_activity(test_node,test_user,base_topic,mqtt_opts)
  send_inactivity(test_node,test_user,base_topic,mqtt_opts)
  send_logout(test_node,test_user,base_topic,mqtt_opts)
  send_issue(test_node,test_user,"Exploded thrice",base_topic,mqtt_opts)
  send_poweroff(test_node,base_topic,mqtt_opts)
