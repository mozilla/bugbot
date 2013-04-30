#!/usr/bin/env python
"""
A script for automated nagging emails listing all the bugs being tracked by certain queries
These can be collated into several 'queries' through the use of multiple query files with 
a 'query_name' param set eg: 'Bugs tracked for Firefox Beta (13)'
Once the bugs have been collected from bugzilla they are sorted into buckets by assignee manager
and an email can be sent out to the assignees, cc'ing their manager about which bugs are being tracked
for each query
"""
import sys, os
import json
import smtplib
import time
import subprocess
import urllib
import tempfile
from datetime import datetime
from dateutil.parser import parse
from argparse import ArgumentParser
from bugzilla.agents import BMOAgent
from bugzilla.utils import get_credentials
from bugzilla.models import DATETIME_FORMAT, DATETIME_FORMAT_WITH_SECONDS
import phonebook
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))

REPLY_TO_EMAIL = 'release-mgmt@mozilla.com'
EMAIL_SUBJECT = ''
SMTP = 'smtp.mozilla.org'
people = phonebook.PhonebookDirectory()

# TODO - write tests!
# TODO - look into knocking out duplicated bugs in queries -- perhaps print out if there are dupes in queries when queries > 1
# TODO - should compare bugmail from API results to phonebook bugmail in to_lower()

def get_last_manager_comment(comments, manager):
    # go through in reverse order to get most recent
    for comment in comments[::-1]:
        if person != None:
            if comment.creator.name == manager['mozillaMail'] or comment.creator.name == manager['bugzillaEmail']:
                return comment.creation_time.replace(tzinfo=None)
    return None

def get_last_assignee_comment(comments, person):
    # go through in reverse order to get most recent
    for comment in comments[::-1]:
        if person != None:
            if comment.creator.name == person['mozillaMail'] or comment.creator.name == person['bugzillaEmail']:
                return comment.creation_time.replace(tzinfo=None)
    return None

def query_url_to_dict(url):
    if (';')in url:
        fields_and_values = url.split("?")[1].split(";")
    else:
        fields_and_values = url.split("?")[1].split("&")
    d = {}

    for pair in fields_and_values:
        (key,val) = pair.split("=")
        if key != "list_id":
            d[key]=urllib.unquote(val)
    return d

def generateEmailOutput(subject, queries, template, show_comment=False, manager_email=None, 
                    cc_list=None, to_addrs=None):
    template_params = {}
    toaddrs = []
    cclist = []

    # stripping off the templates dir, just in case it gets passed in the args
    template = env.get_template(template.replace('templates/', '', 1))
    def addToAddrs(bug):
        if people.people_by_bzmail.has_key(bug.assigned_to.name):
            person = dict(people.people_by_bzmail[bug.assigned_to.name])
            if person['mozillaMail'] not in toaddrs:
                toaddrs.append(person['mozillaMail'])

    for query in queries.keys():
        if not template_params.has_key(query):
            template_params[query] = {'buglist': []}
        for bug in queries[query]['bugs']:
            if queries[query].has_key('show_summary'):
                if queries[query]['show_summary'] == '1':
                    summary=bug.summary
                else:
                    summary = ""
            else:
                summary=""
            template_params[query]['buglist'].append({
                    'id':bug.id,
                    'summary':summary,
                    #'comment': bug.comments[-1].creation_time.replace(tzinfo=None),
                    'assignee': bug.assigned_to.real_name,
                    'flags': bug.flags
            })
            # more hacking for JS special casing
            if bug.assigned_to.name == 'general@js.bugs' and 'nihsanullah@mozilla.com' not in toaddrs:
                toaddrs.append('nihsanullah@mozilla.com')
            # if needinfo? in flags, add the flag.requestee to the toaddrs instead of bug assignee
            if bug.flags:
                for flag in bug.flags:
                    if 'needinfo' in flag.name and flag.status == '?':
                        try:
                            person = dict(people.people_by_bzmail[str(flag.requestee)])
                            if person['mozillaMail'] not in toaddrs:
                                toaddrs.append(person['mozillaMail'])
                        except:
                            if str(flag.requestee) not in toaddrs:
                                toaddrs.append(str(flag.requestee))
                    else:
                        addToAddrs(bug)
            else:
                addToAddrs(bug)

                    
    message_body = template.render(queries=template_params, show_comment=show_comment)
    if manager_email != None:
        cclist.append(manager_email)
    # no need to and cc the manager if more than one email 
    if len(toaddrs) > 1:
        for email in toaddrs:
            if email in cclist:
                toaddrs.remove(email)

    if to_addrs != None:
        toaddrs = to_addrs

    message = ("From: %s\r\n" % REPLY_TO_EMAIL
        + "To: %s\r\n" % ",".join(toaddrs)
        + "CC: %s\r\n" % ",".join(cclist + cc_list)
        + "Subject: %s\r\n" % subject
        + "\r\n" 
        + message_body)
    toaddrs = toaddrs #+ cc_list

    return toaddrs,message


def sendMail(toaddrs,msg,username,password,dryrun=False):
    if dryrun:
        print "\n****************************\n* DRYRUN: not sending mail *\n****************************\n"
        print msg
    else:
        server = smtplib.SMTP_SSL(SMTP, 465)
        server.set_debuglevel(1)
        server.login(username, password)
        # note: toaddrs is required for transport agents, the msg['To'] header is not modified
        server.sendmail(username,toaddrs, msg)
        server.quit()

if __name__ == '__main__':
    parser = ArgumentParser(__doc__)
    parser.set_defaults(
        dryrun=False,
        username=None,
        password=None,
        roll_up=False,
        show_comment=False,
        email_cc_list=[],
        queries=[],
        days_since_comment=-1,
        verbose=False,
        keywords=None,
        email_subject=None,
        no_verification=False,
        )
    parser.add_argument("-d", "--dryrun", dest="dryrun", action="store_true",
            help="just do the query, and print emails to console without emailing anyone")
    parser.add_argument("-m", "--mozilla-email", dest="mozilla_mail",
            help="specify a specific address for sending email"),
    parser.add_argument("-p", "--email-password", dest="email_password",
            help="specify a specific password for sending email")
    parser.add_argument("-t", "--template", dest="template", 
            required=True,
            help="template to use for the buglist output")
    parser.add_argument("-e", "--email-cc-list", dest="email_cc_list",
            action="append",
            help="email addresses to include in cc when sending mail")
    parser.add_argument("-q", "--query", dest="queries",
            action="append", 
            required=True,
            help="a file containing a dictionary of a bugzilla query")
    parser.add_argument("-k", "--keyword", dest="keywords",
            action="append",
            help="keywords to collate buglists")
    parser.add_argument("-s", "--subject", dest="email_subject", 
            required=True,
            help="The subject of the email being sent")
    parser.add_argument("-r", "--roll-up", dest="roll_up", action="store_true",
            help="flag to get roll-up output in one email instead of creating multiple emails")
    parser.add_argument("--show-comment", dest="show_comment", action="store_true",
            help="flag to display last comment on a bug in the message output")
    parser.add_argument("--days-since-comment", dest="days_since_comment",
            help="threshold to check comments against to take action based on days since comment")
    parser.add_argument("--verbose", dest="verbose", action="store_true",
            help="turn on verbose output")
    parser.add_argument("--no-verification", dest="no_verification", action="store_true",
            help="don't wait for human verification of every email")

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
    
    # Get the buglist(s)
    collected_queries = {}
    for query in options.queries:
        # import the query
        if os.path.exists(query):
            info = {}
            execfile(query, info)
            query_name = info['query_name']
            if not collected_queries.has_key(query_name):
                collected_queries[query_name] = {
                    'channel': info.get('query_channel', ''),
                    'bugs' : [],
                    'show_summary': info.get('show_summary', 0),
                    }
            if info.has_key('query_params'):
                print "Gathering bugs from query_params in %s" % query
                collected_queries[query_name]['bugs'] = bmo.get_bug_list(info['query_params'])
            elif info.has_key('query_url'):
                print "Gathering bugs from query_url in %s" % query
                collected_queries[query_name]['bugs'] = bmo.get_bug_list(query_url_to_dict(info['query_url'])) 
            else:
                print "Error - no valid query params or url in the config file"
                sys.exit(1)
        else:
            print "Not a valid path: %s" % query
    total_bugs = 0
    for channel in collected_queries.keys():
        total_bugs += len(collected_queries[channel]['bugs'])

    print "Found %s bugs total for %s queries" % (total_bugs, len(collected_queries.keys()))
    print "Queries to collect: %s" % collected_queries.keys()

    managers = people.managers
    manual_notify = {}
    counter = 0

    def add_to_managers(manager_email, query, info={}):
        if not managers.has_key(manager_email):
            managers[manager_email] = {}
            managers[manager_email]['nagging'] = {
                    query : { 'bugs': [bug], 'show_summary': info.get('show_summary', 0) },
                }
            return
        if managers[manager_email].has_key('nagging'):
            if managers[manager_email]['nagging'].has_key(query):
                managers[manager_email]['nagging'][query]['bugs'].append(bug)
                if options.verbose:
                    print "Adding %s to %s in nagging for %s" % (bug.id, query, manager_email)
            else:
                managers[manager_email]['nagging'][query] = { 'bugs': [bug], 'show_summary': info.get('show_summary', 0) }
                if options.verbose:
                    print "Adding new query key %s for bug %s in nagging and %s" % (query, bug.id, manager_email)
        else:
            managers[manager_email]['nagging'] = {
                    query : { 'bugs': [bug], 'show_summary': info.get('show_summary', 0) },
                }
            if options.verbose:
                print "Creating query key %s for bug %s in nagging and %s" % (query, bug.id, manager_email)
    
    for query, info in collected_queries.items():
        manual_notify[query] = { 'bugs': [], 'show_summary': info.get('show_summary',0)}
        for b in collected_queries[query]['bugs']:
            counter = counter + 1
            send_mail = True
            bug = bmo.get_bug(b.id)
            manual_notify[query]['bugs'].append(bug)
            assignee = bug.assigned_to.name
            if people.people_by_bzmail.has_key(assignee):
                person = dict(people.people_by_bzmail[assignee])
            else:
                person = None
            
            # kick bug out if days since comment check is on
            if options.days_since_comment != -1:
                # try to get last_comment by assignee & manager
                if person != None:
                    last_comment = get_last_assignee_comment(bug.comments, person)
                    if person.has_key('manager') and person['manager'] != None:
                        manager_email = person['manager']['dn'].split('mail=')[1].split(',')[0]
                        manager = people.people[manager_email]
                        last_manager_comment = get_last_manager_comment(bug.comments, people.people_by_bzmail[manager['bugzillaEmail']])
                        # set last_comment to the most recent of last_assignee and last_manager
                        if last_manager_comment != None and last_comment != None and last_manager_comment > last_comment:
                            last_comment = last_manager_comment
                # otherwise just get the last comment
                else:
                    last_comment = bug.comments[-1].creation_time.replace(tzinfo=None)
                if last_comment != None:
                    timedelta = datetime.now() - last_comment
                    if timedelta.days <= int(options.days_since_comment):
                        if options.verbose:
                            print "Skipping bug %s since it's had an assignee or manager comment within the past %s days" % (bug.id, options.days_since_comment)
                        send_mail = False
                        counter = counter - 1
                        manual_notify[query]['bugs'].remove(bug)
                    else:
                        if options.verbose:
                            print "This bug needs notification, it's been %s since last comment of note" % timedelta.days
    
            if send_mail:
                if 'nobody' in assignee:
                    if options.verbose:
                        print "No one assigned to: %s, will be in the manual notification list..." % bug.id
                # TODO - get rid of this, SUCH A HACK!
                elif 'general@js.bugs' in assignee:
                    if options.verbose:
                        print "No one assigned to JS bug: %s, adding to Naveed's list..." % bug.id
                    add_to_managers('nihsanullah@mozilla.com', query, info)
                else:
                    if bug.assigned_to.real_name != None:
                        if person != None:
                            # check if assignee is already a manager, add to their own list
                            if managers.has_key(person['mozillaMail']):
                                add_to_managers(person['mozillaMail'], query, info)
                            # otherwise we search for the assignee's manager
                            else:
                                # check for manager key first, a few people don't have them
                                if person.has_key('manager') and person['manager'] != None:
                                    manager_email = person['manager']['dn'].split('mail=')[1].split(',')[0]
                                    if managers.has_key(manager_email):
                                        add_to_managers(manager_email, query, info)
                                    elif people.vices.has_key(manager_email):
                                        # we're already at the highest level we'll go
                                        if managers.has_key(assignee):
                                            add_to_managers(assignee, query, info)
                                        else:
                                            if options.verbose:
                                                print "%s has a V-level for a manager, and is not in the manager list" % assignee
                                            managers[person['mozillaMail']] = {}
                                            add_to_managers(person['mozillaMail'], query, info)
                                    else:
                                        # try to go up one level and see if we find a manager
                                        if people.people.has_key(manager_email):
                                            person = dict(people.people[manager_email])
                                            manager_email = person['manager']['dn'].split('mail=')[1].split(',')[0]
                                            if managers.has_key(manager_email):
                                                add_to_managers(manager_email, query, info)
                                        else:
                                            print "Manager could not be found: %s" % manager_email
                                # if you don't have a manager listed, but are an employee, we'll nag you anyway
                                else:
                                    add_to_managers(person['mozillaMail'], query, info)
                                    print "%s's entry doesn't list a manager! Let's ask them to update phonebook but in the meantime they get the email directly." % person['name']

    if options.roll_up:
        # only send one email
        toaddrs,msg = generateEmailOutput(
                    subject=options.email_subject,
                    queries=manual_notify,
                    template=options.template,
                    show_comment=options.show_comment,
                    cc_list=options.email_cc_list,
                    to_addrs=['b2g-release-drivers@mozilla.org'])
        if options.email_password == None or options.mozilla_mail == None:
            print "Please supply a username/password (-m, -p) for sending email"
            sys.exit(1)
        if not options.dryrun:
            print "SENDING EMAIL"
        sendMail(toaddrs,msg,options.mozilla_mail,options.email_password,options.dryrun)
    else:
        # Get yr nag on!
        for email, info in managers.items():
            inp = ''
            if info.has_key('nagging'):
                toaddrs,msg = generateEmailOutput(
                    subject=options.email_subject,
                    manager_email=email,
                    queries=info['nagging'],
                    template=options.template,
                    show_comment=options.show_comment,
                    cc_list=options.email_cc_list)
                while True and not options.no_verification:
                    print "\nRelMan Nag is ready to send the following email:\n<------ MESSAGE BELOW -------->"
                    print msg
                    print "<------- END MESSAGE -------->\nWould you like to send now?"
                    inp = raw_input('\n Please select y/Y to send, v/V to edit, or n/N to skip and continue to next email: ')
    
                    if  inp != 'v' and inp != 'V':
                        break
    
                    tempfilename = tempfile.mktemp()
                    temp_file = open(tempfilename, 'w')
                    temp_file.write(msg)
                    temp_file.close()
    
                    subprocess.call(['vi', tempfilename])
    
                    temp_file = open(tempfilename,'r')
                    msg = temp_file.read()
                    toaddrs=msg.split("To: ")[1].split("\r\n")[0].split(',') + msg.split("CC: ")[1].split("\r\n")[0].split(',')
                    os.remove(tempfilename)
    
                if inp == 'y' or inp == 'Y' or options.no_verification:
                    if options.email_password == None or options.mozilla_mail == None:
                        print "Please supply a username/password (-m, -p) for sending email"
                        sys.exit(1)
                    if not options.dryrun:
                        print "SENDING EMAIL"
                    sendMail(toaddrs,msg,options.mozilla_mail,options.email_password,options.dryrun)
                    sent_bugs = 0
                    for query, info in info['nagging'].items():
                        sent_bugs += len(info['bugs'])
                        # take sent bugs out of manual notification list
                        for bug in info['bugs']:
                            manual_notify[query]['bugs'].remove(bug)
                    counter = counter - sent_bugs
    
if not options.roll_up:
    emailed_bugs = []
    # Send RelMan the manual notification list only when there are bugs that didn't go out
    msg_body = """\n*************\nNo nag emails were generated for these bugs because 
they are either assigned to no one or to non-employees (though ni? on non-employees will get nagged). 
\nYou will need to look at the following bugs:\n*************\n\n"""
    for k,v in manual_notify.items():
        if len(v['bugs']) != 0:
            for bug in v['bugs']:
                if bug.id not in emailed_bugs:
                    if k not in msg_body:
                        msg_body += "\n=== %s ===\n" % k
                    emailed_bugs.append(bug.id)
                    msg_body +="http://bugzil.la/" + "%s -- assigned to: %s\n -- Last commented on: %s\n" % (bug.id, bug.assigned_to.real_name, bug.comments[-1].creation_time.replace(tzinfo=None))
                msg = ("From: %s\r\n" % REPLY_TO_EMAIL
                    + "To: %s\r\n" % REPLY_TO_EMAIL
                    + "Subject: RelMan Attention Needed: %s\r\n" % options.email_subject
                    + "\r\n" 
                    + msg_body)
    sendMail(['release-mgmt@mozilla.com'], msg, options.mozilla_mail, options.email_password, options.dryrun)

