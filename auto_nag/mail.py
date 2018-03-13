# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from os.path import basename
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
import six
import smtplib


SMTP = 'smtp.mozilla.org'
PORT = 465


def send(From, To, Subject, Body,
         Cc=[], Bcc=[], html=False,
         files=[], login={}, dryrun=False):
    """Send an email
    """
    if isinstance(To, six.string_types):
        To = [To]
    if isinstance(Cc, six.string_types):
        Cc = [Cc]
    if isinstance(Bcc, six.string_types):
        Bcc = [Bcc]

    if dryrun:
        print('\n****************************')
        print('* DRYRUN: not sending mail *')
        print('****************************\n')
        print('Receivers: {}'.format(To + Cc + Bcc))
        print('Subject: {}'.format(Subject))
        print('Body:')
        print(Body)
        return

    subtype = 'html' if html else 'plain'
    message = MIMEMultipart()
    message['From'] = From
    message['To'] = ', '.join(To)
    message['Subject'] = Subject
    message['Cc'] = ', '.join(Cc)
    message['Bcc'] = ', '.join(Bcc)

    message.attach(MIMEText(Body, subtype))

    for f in files:
        with open(f, "rb") as In:
            f = basename(f)
            part = MIMEApplication(In.read(), Name=basename(f))
            part['Content-Disposition'] = 'attachment; filename="%s"' % f
            message.attach(part)

    mailserver = smtplib.SMTP(SMTP, PORT)
    mailserver.set_debuglevel(1)
    if login:
        username = login.get('ldap_username')
        password = login.get('ldap_password')
        if username and password:
            mailserver.login(username, password)

    mailserver.sendmail(From, To, message.as_string())
    mailserver.quit()
