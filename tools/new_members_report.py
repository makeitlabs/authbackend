import sqlite3
import json
import time
from slacker import Slacker
import ConfigParser
import argparse
import string

parser = argparse.ArgumentParser(description='Weekly new members report script')
parser.add_argument('--ini', help='location of .ini file')
parser.add_argument('--days', type=int, default=7)
parser.add_argument('--test', default=False, help='test output, do not send to slack')
args = parser.parse_args()

print args.days

Config = ConfigParser.ConfigParser()
Config.read(args.ini)

SlackToken = Config.get('SlackReporter', 'BOT_API_TOKEN')
SlackChannel = Config.get('SlackReporter', 'BOT_CHANNEL')
SlackUser= Config.get('SlackReporter', 'BOT_NAME')

def sendMsg(timestamp, text):
    if timestamp == 'now':
        timestamp = time.strftime('%B %d %H:%M:%S %Z', time.localtime())

    attachments = []
    attachment_data = { 'text': text, 'mrkdwn_in':['text', 'pretext'] }
    attachments.append(attachment_data)

    if args.test:
        print json.dumps(attachments)
    else:
        slack.chat.post_message(SlackChannel, '_' + timestamp + '_', username=SlackUser, attachments=json.dumps(attachments))

# init slack
slack = Slacker(SlackToken)

conn = sqlite3.connect('/var/www/authbackend-ng/makeit.db')

c = conn.cursor()

count = 0
msg = ''

for row in c.execute('''SELECT member,time_created from members where time_created between datetime('now',?) and datetime('now')''', ('-%d days' % args.days,)):
    msg = msg + row[0] + ' created on ' + row[1] + '\n'
    count = count + 1

msg = ('\n%d total created in past %d days\n\n' % (count, args.days)) + msg

sendMsg('now', msg)
