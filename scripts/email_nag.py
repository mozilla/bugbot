#!/usr/bin/env python
"""%prog [-d|--dryrun] [-u|--username `username`] [-p|--password `password`]
        [-V| --version `version`]
        [-e|--email-cc-list `email@address.com`]
        [--verbose]

"""
import json
import smtplib
from datetime import datetime
from dateutil.parser import parse
from argparse import ArgumentParser
from bugzilla.agents import BMOAgent
from bugzilla.utils import get_credentials
from bugzilla.models import DATETIME_FORMAT, DATETIME_FORMAT_WITH_SECONDS
import phonebook

FROM_EMAIL = 'release-mgmt@mozilla.com'
SMTP = 'smtp.mozilla.org'

# TODO - pull a variety of queries from passed in json file(s) instead of hardcoding here
query_params = {
        'field0-0-0':   'cf_tracking_firefox12',
        'field0-1-0':   'cf_status_firefox12',
        'field0-2-0':   'cf_status_firefox12',
        'field0-4-0':   'cf_status_firefox12',
        'field0-3-0':   'cf_status_firefox12',
        'query_format': 'advanced',
        'value0-2-0':   'fixed',
        'type0-1-0':    'notequals',
        'value0-4-0':   'verified',
        'emailtype1':   'notequals',
        'value0-3-0':   'unaffected',
        'emailassigned_to1':    '1',
        'value0-1-0':   'wontfix',
        'email1':   'administration@bugzilla.bugs',
        'type0-0-0':    'equals',
        'value0-0-0':   '+',
        'type0-2-0':    'notequals',
        'type0-4-0':    'notequals',
        'type0-3-0':    'notequals'
}

def createEmail(manager_email, bugs, version, cc_list=None):
    # TESTING ONLY - to be removed
    if manager_email == 'joduinn@mozilla.com':
        manager_email = 'lsblakk@mozilla.com'
    if cc_list == None:
        cc_list = [manager_email, FROM_EMAIL]
    toaddrs = []

    message_body ='''
We're currently getting in touch with teams that have unfixed bugs tracked for Firefox %s assigned to them. 

Here's your list:\n
''' % version

    for bug in bugs:
        message_body += '%s - assigned to: %s\n\tLast commented on: %s\n' % (bug, bug.assigned_to.real_name, bug.comments[-1].creation_time.replace(tzinfo=None))
        if bug.assigned_to.name != 'general@js.bugs':
            if bug.assigned_to.name not in toaddrs:
                toaddrs.append(bug.assigned_to.name)

    message_body +='''
Please either make the case for untracking, let us know what is blocking the 
investigation, or make sure the above issues are prioritized for release. Thanks!

Sincerely,
Release Managment Team'''

    message_subject = 'Bugs Tracked for Firefox %s' % version
    message = ("From: %s\r\n" % FROM_EMAIL
        + "To: %s\r\n" % ",".join(toaddrs)
        + "CC: %s\r\n" % ",".join(cc_list)
        + "Subject: %s\r\n" % message_subject
        + "\r\n" 
        + message_body)
    toaddrs = toaddrs + cc_list
    return toaddrs,message

def sendMail(toaddrs,msg,dryrun=False):
    if dryrun:
        print "DRYRUN: not sending mail: %s" % msg
    else:
        server = smtplib.SMTP(SMTP)
        server.set_debuglevel(1)
        server.sendmail(FROM_EMAIL,toaddrs, msg)
        server.quit()

if __name__ == '__main__':
    parser = ArgumentParser(__doc__)
    parser.set_defaults(
        dryrun=False,
        username=None,
        password=None,
        version=None,
        verbose=False,
        email_cc_list=['release-mgmt@mozilla.com'],
        days_since_comment=-1,
        )
    parser.add_argument("-d", "--dryrun", dest="dryrun", action="store_true",
            help="just do the query, and print emails to console without emailing anyone")
    parser.add_argument("-u", "--username", dest="username",
            help="specify a specific username for bugzilla")
    parser.add_argument("-V", "--version", dest="version",
            help="firefox version string for tracking", required=True)
    parser.add_argument("-e", "--email-cc-list", dest="email_cc_list",
            action="append",
            help="email addresses to include in cc when sending mail")
    parser.add_argument("--days-since-comment", dest="days_since_comment",
            help="threshold to check comments against to take action based on days since comment")
    parser.add_argument("--verbose", dest="verbose", action="store_true",
            help="threshold to check comments against to take action based on days since comment")

    options, args = parser.parse_known_args()
    
    if not options.username:
        # We can use "None" for both instead to not authenticate
        username, password = get_credentials()
    else:
        username, password = get_credentials(username)
    try:
        int(options.days_since_comment)
    except:
        if options.days_since_comment != None:
            parser.error("Need to provide a number for days since last comment value")

    # Load our agent for BMO
    bmo = BMOAgent(username, password)
    
    # Get the bugs for the requested query_params
    buglist = bmo.get_bug_list(query_params)
    print "Found %s bugs" % (len(buglist))
    
    people = phonebook.PhonebookDirectory()
    managers = people.managers
    manual_notify = []
    counter = 0

    def add_to_managers(manager_email):
        if managers[manager_email].has_key('nagging'):
            managers[manager_email]['nagging'].append(bug)
        else:
            managers[manager_email]['nagging'] = [bug]

    for b in buglist:
        # TODO - check security status of bug
        counter = counter + 1
        send_mail = True
        bug = bmo.get_bug(b.id)
        manual_notify.append(bug)
        assignee = bug.assigned_to.name
        
        # how many days since comment
        if options.days_since_comment != -1:
            last_comment = bug.comments[-1].creation_time.replace(tzinfo=None)
            timedelta = datetime.now() - last_comment
            if timedelta.days <= int(options.days_since_comment):
                if options.verbose:
                    print "Skipping bug %s since it's had a comment within the past %s days" % (bug.id, options.days_since_comment)
                send_mail = False
                counter = counter - 1
                manual_notify.pop(bug)

        if send_mail:
            if 'nobody' in assignee:
                if options.verbose:
                    print "No one assigned to: %s, adding to manual notification list..." % bug.id
                assignee = None
            elif 'general@js.bugs' in assignee:
                if options.verbose:
                    print "No one assigned to JS bug: %s, adding to dmandelin's list..." % bug.id
                add_to_managers('dmandelin@mozilla.com')
            else:
                if bug.assigned_to.real_name != None:
                    if people.people_by_bzmail.has_key(assignee):
                        person = dict(people.people_by_bzmail[assignee])
                        # check if assignee is already a manager
                        if managers.has_key(person['bugzillaEmail']):
                            add_to_managers(person['bugzillaEmail'])
                        # otherwise we dig up the assignee's manager
                        else:
                            manager_email = person['manager']['dn'].split('mail=')[1].split(',')[0]
                            if managers.has_key(manager_email):
                                add_to_managers(manager_email)
                            elif people.vices.has_key(manager_email):
                                # we're already at the highest level we'll go
                                if managers.has_key(assignee):
                                    add_to_managers(assignee)
                                else:
                                    if options.verbose:
                                        print "%s has a V-level for a manager, and is not in the manager list" % assignee
                                    # Maybe we want to send out a Group email here? Team accountability?  Or send to Damon?
                            else:
                                # try to go up one level and see if we find a manager
                                if people.people.has_key(manager_email):
                                    person = dict(people.people[manager_email])
                                    manager_email = person['manager']['dn'].split('mail=')[1].split(',')[0]
                                    if managers.has_key(manager_email):
                                        add_to_managers(manager_email)
                                else:
                                    print "Manager could not be found: %s" % manager_email

    # Get yr nag on!
    for email, info in managers.items():
        if info.has_key('nagging'):
            print "\nRelMan Nag is ready to send the following email:\n<------ MESSAGE BELOW -------->"
            toaddrs,msg = createEmail(manager_email=email, bugs=info['nagging'], version=options.version)
            print msg
            print "<------- END MESSAGE -------->\nWould you like to send now?"
            inp = raw_input('\n Please select y/Y to send or n/N to skip and continue to next email: ')
            if inp == 'y' or inp == 'Y':
                print "SENDING EMAIL"
                sendMail(toaddrs,msg,options.dryrun)
                counter = counter - len(info['nagging'])
                # take sent bugs out of manual notification list
                for bug in info['nagging']:
                    manual_notify.remove(bug)

    # Here's the manual notification list
    print "\n*************\nNo email generated for %s/%s bugs, you will need to manually notify the following %s bugs:\n" % (counter, len(buglist), len(manual_notify))
    url = "https://bugzilla.mozilla.org/buglist.cgi?quicksearch="
    for bug in manual_notify:
        print "%s - assigned to: %s\n\tLast commented on: %s\n" % (bug, bug.assigned_to.real_name, bug.comments[-1].creation_time.replace(tzinfo=None))
        url += "%s," % bug.id
    print "Url for manual notification bug list: %s" % url

