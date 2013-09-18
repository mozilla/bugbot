# Post-Mortem and Sign-off automated reminder
# Daily cronjob, 6am PT

import urllib2
import datetime
import re
import os
import json
import smtplib

REPLY_TO_EMAIL = 'release-mgmt@mozilla.com'
SMTP = 'smtp.mozilla.org'
CONFIG_JSON = os.getcwd() + "/bztools/scripts/configs/config.json"
config = json.load(open(CONFIG_JSON, 'r'))
scripts_dir = os.getcwd() + "/scripts/"

subject = None
toaddrs = ['dev-planning@lists.mozilla.org', 'release-drivers@mozilla.com']


def sendMail(toaddr, options):
    message = ("From: %s\r\n" % options['username']
        + "To: %s\r\n" % toaddr
        + "CC: %s\r\n" % options['cclist']
        + "Reply-To: %s\r\n" % REPLY_TO_EMAIL
        + "Subject: %s\r\n" % options['subject']
        + "\r\n"
        + options['body'])

    server = smtplib.SMTP_SSL(SMTP, 465)
    server.set_debuglevel(1)
    server.login(options['username'], options['password'])
    # note: toaddrs is required for transport agents, the msg['To'] header is not modified
    server.sendmail(options['username'], toaddr, message)
    server.quit()


def getTemplateValue(url):
    version_regex = re.compile(".*<p>(.*)</p>.*")
    template_page = urllib2.urlopen(url).read().replace('\n', '')
    parsed_template = version_regex.match(template_page)
    return parsed_template.groups()[0]

# Grab the release date, the beta version number
release_date = getTemplateValue("https://wiki.mozilla.org/Template:FIREFOX_SHIP_DATE")
beta_version = getTemplateValue("https://wiki.mozilla.org/Template:BETA_VERSION")
current_version = getTemplateValue("https://wiki.mozilla.org/Template:CURRENT_VERSION")
today = datetime.date.today()
release = datetime.datetime.strptime(release_date, "%B %d, %Y").date()

# Check the timedelta between today and releasedate and if:
# -7 days before release date Sign Off reminder for 'tomorrow': Wed at 10am PT
# -29 days before next release date send Post-Mortem for the previous version 'tomorrow': Tues at 9am PT)
timedelta = today - release

if timedelta.days == -7:
    # send the reminder email for sign off meeting
    print "Sending Sign-off email reminder %s" % today
    subject = "Automatic Reminder: Firefox %s Sign Off Meeting" % beta_version
    body = """
This is a reminder that the FF%s sign-off meeting will be held tomorrow in the Release Coordination Vidyo room @ 10:00 am PT.

The wiki page is up and ready for you to add notes : https://wiki.mozilla.org/Releases/Firefox_%s/Final_Signoffs

-- Release Management
""" % (beta_version, beta_version)
if timedelta.days == -29:
    # send the reminder email for post-mortem of curent release version
    print "Sending post-mortem email reminder %s" % today
    subject = "Reminder: Firefox %s Post Mortem Meeting Tomorrow" % current_version
    body = """
Friendly Reminder that the FF%s.0 Post-Mortem will take place tomorrow @ 9:00 am PT in the Release Co-ordination Vidyo room.

Etherpad - https://etherpad.mozilla.org/%s-0-Post-Mortem

-- Release Management
""" % (current_version, current_version)

if subject is not None:
    options = {
        "username": config['ldap_username'],
        "password": config['ldap_password'],
        "subject": subject,
        "body": body,
        "cclist": "release-mgmt@mozilla.com",
        "toaddrs": toaddrs
    }
    for email in toaddrs:
        sendMail(email, options)
else:
    print "No command today: %s" % today
