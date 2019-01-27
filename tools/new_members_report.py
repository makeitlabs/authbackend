import sqlite3
import json
import time
from slacker import Slacker

SlackChannel = '<Slack Channel>'
SlackUser = '<Slack User>'
SlackToken = '<Slack Token>'
DBFILE = '/var/www/authbackend/makeit.db'

def sendMsg(timestamp, text):
    if timestamp == 'now':
        timestamp = time.strftime('%B %d %H:%M:%S %Z', time.localtime())

    attachments = []
    attachment_data = { 'text': text, 'mrkdwn_in':['text', 'pretext'] }
    attachments.append(attachment_data)

    slack.chat.post_message(SlackChannel, '_' + timestamp + '_', username=SlackUser, attachments=json.dumps(attachments))

# init slack
slack = Slacker(SlackToken)

conn = sqlite3.connect(DBFILE)

c = conn.cursor()

numdays = 7
count = 0
msg = ''

for row in c.execute('''SELECT member,created_date from members where created_date between datetime('now',?) and datetime('now')''', ('-%d days' % numdays,)):
    msg = msg + row[0] + ' created on ' + row[1] + '\n'
    count = count + 1

msg = ('\n%d total created in past %d days\n\n' % (count, numdays)) + msg

sendMsg('now', msg)
