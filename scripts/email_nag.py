#!/usr/bin/env python
"""%prog [-d|--dryrun] [-u|--username `username`] [-p|--password `password`]
        [-V| --version `version`]
        [-e|--email-cc-list `email@address.com`]
        [--verbose]

"""
import sys, os
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
people = phonebook.PhonebookDirectory()

# DONE - get last comment, but also walk up the comments to last assignee comment
# TODO - pass in more than one version, organize email template to coallesce emails, Beta first, then Aurora
# DONE - pull a variety of queries from passed files

def get_last_assignee_comment(comments, person):
    for comment in comments[::-1]:
        if person != None:
            if comment.creator.name == person['mozillaMail'] or comment.creator.name == person['bugzillaEmail']:
                print "Returning %s's last comment on their bug." % comment.creator.real_name
                return comment.creation_time.replace(tzinfo=None)
    return None

def createEmail(manager_email, bugs, version, cc_list=None):
    if cc_list == None:
        cc_list = [manager_email, FROM_EMAIL]
    toaddrs = []

    message_body ='''
We're currently getting in touch with teams that have unfixed bugs tracked for Firefox %s assigned to them. 

Here's your list:\n
''' % version

    for bug in bugs:
        message_body += '%s -- assigned to: %s -- Last commented on: %s\n' % (bug, bug.assigned_to.real_name, bug.comments[-1].creation_time.replace(tzinfo=None))
        if bug.assigned_to.name != 'general@js.bugs':
            # we will email people at their LDAP email, not bugmail
            person = dict(people.people_by_bzmail[bug.assigned_to.name])
            if person['mozillaMail'] not in toaddrs:
                toaddrs.append(person['mozillaMail'])

    message_body +='''
Please either make the case for untracking, let us know what is blocking the 
investigation, or make sure the above issues are prioritized for release. Thanks!

Sincerely,
Release Management Team'''

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
        template=None,
        wiki=False,
        email_cc_list=['release-mgmt@mozilla.com'],
        queries=[],
        days_since_comment=-1,
        verbose=False,
        )
    parser.add_argument("-d", "--dryrun", dest="dryrun", action="store_true",
            help="just do the query, and print emails to console without emailing anyone")
    parser.add_argument("-u", "--username", dest="username",
            help="specify a specific username for bugzilla")
    parser.add_argument("-V", "--version", dest="version",
            help="firefox version string for tracking", required=True)
    parser.add_argument("-t", "--template", dest="template",
            help="jinja template to use for the email or wiki page to create")
    parser.add_argument("--wiki", dest="wiki", action="store_true",
            help="flag to set wiki output instead of email")
    parser.add_argument("-e", "--email-cc-list", dest="email_cc_list",
            action="append",
            help="email addresses to include in cc when sending mail")
    parser.add_argument("-q", "--query", dest="queries",
            action="append",
            help="a file containing a dictionary of a bugzilla query")
    parser.add_argument("--days-since-comment", dest="days_since_comment",
            help="threshold to check comments against to take action based on days since comment")
    parser.add_argument("--verbose", dest="verbose", action="store_true",
            help="threshold to check comments against to take action based on days since comment")

    options, args = parser.parse_known_args()
    
    if options.queries == []:
        parser.error("Need to provide at least one query to run")
    
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
    
    # Get the buglist(s)
    collected_channels = {}
    for query in options.queries:
        # import the query
        if os.path.exists(query):
            info = {}
            execfile(query, info)
            channel = info['channel']
            collected_channels[channel] = {
                'priority' : info.get('priority', 1),
                'buglist' : [],
                }
            collected_channels[channel]['buglist'] = bmo.get_bug_list(info['query_params'])
        else:
            print "Not a valid path: %s" % query
    total_bugs = 0
    for channel in collected_channels.keys():
        total_bugs += len(collected_channels[channel]['buglist'])
    print "Found %s bugs total." % total_bugs
    print collected_channels.keys()
    sys.exit(0)
    
    managers = people.managers
    manual_notify = []
    counter = 0

    def add_to_managers(manager_email):
        if managers[manager_email].has_key('nagging'):
            managers[manager_email]['nagging'].append(bug)
        else:
            managers[manager_email]['nagging'] = [bug]
    
    # TODO - now go through each channel and build the notifications, then come back for template selection & creation of output (email/wiki)
    for b in buglist:
        counter = counter + 1
        send_mail = True
        bug = bmo.get_bug(b.id)
        manual_notify.append(bug)
        assignee = bug.assigned_to.name
        if people.people_by_bzmail.has_key(assignee):
            person = dict(people.people_by_bzmail[assignee])
        else:
            person = None
        
        # kick bug out if days since comment check is on
        if options.days_since_comment != -1:
            # try to get last_comment by assignee
            if person != None:
                last_comment = get_last_assignee_comment(bug.comments, person)
            # otherwise just get the last comment
            else:
                last_comment = bug.comments[-1].creation_time.replace(tzinfo=None)
            if last_comment != None:
                print bug.comments[-1].creator.name, bug.comments[-1].creator.real_name
                timedelta = datetime.now() - last_comment
                if timedelta.days <= int(options.days_since_comment):
                    if options.verbose:
                        print "Skipping bug %s since it's had a comment within the past %s days" % (bug.id, options.days_since_comment)
                    send_mail = False
                    counter = counter - 1
                    manual_notify.remove(bug)
                else:
                    print timedelta.days
                    if options.verbose:
                        print "This bug needs notification, it's been %s since last comment of note" % timedelta.days

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
                    if person != None:
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
                                    managers[person['mozillaMail']] = {}
                                    add_to_managers(person['mozillaMail'])
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
        print "[Bug %s] -- assigned to: %s\n -- Last commented on: %s\n" % (bug.id, bug.assigned_to.real_name, bug.comments[-1].creation_time.replace(tzinfo=None))
        url += "%s," % bug.id
    print "Url for manual notification bug list: %s" % url

