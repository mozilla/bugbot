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
EMAIL_SUBJECT = 'Bugs tracked for Firefox 17 - Soon to be on Beta Channel'
SMTP = 'smtp.mozilla.org'
people = phonebook.PhonebookDirectory()

# TODO - keyword groupings for wiki output (and maybe for emails too?)
# TODO - write tests!
# TODO - look into knocking out duplicated bugs in queries -- perhaps print out if there are dupes in queries when queries > 1
# TODO - for wiki page generation, just post counts of certain query results (and their queries) eg: how many unverified fixed bugs for esr10?

def get_last_manager_comment(comments, manager):
    # go through in reverse order to get most recent
    for comment in comments[::-1]:
        if person != None:
            if comment.creator.name == manager['mozillaMail'] or comment.creator.name == manager['bugzillaEmail']:
                # DEBUG 
                # print "Found last manager (%s) comment on bug. %s" % (comment.creator.real_name, comment.creation_time.replace(tzinfo=None))
                return comment.creation_time.replace(tzinfo=None)
    return None

def get_last_assignee_comment(comments, person):
    # go through in reverse order to get most recent
    for comment in comments[::-1]:
        if person != None:
            if comment.creator.name == person['mozillaMail'] or comment.creator.name == person['bugzillaEmail']:
                # DEBUG
                # print "Found last assignee (%s) comment on bug. %s" % (comment.creator.real_name, comment.creation_time.replace(tzinfo=None))
                return comment.creation_time.replace(tzinfo=None)
    return None

def query_url_to_dict(url):
    fields_and_values = url.split("?")[1].split(";")
    d = {}

    for pair in fields_and_values:
        (key,val) = pair.split("=")
        if key != "list_id":
            d[key]=urllib.unquote(val)

    return d

def generateWikiOutput(queries, template, managers=None, keywords=None, days_since_comment=-1):
    """ TODO: reorganize the dictionary based on wiki request
    channel_info = {
            'name': {
                'managers': {
                    'bugs': [],
                    'name': "manager_name",
                },
                
                # keyword bug lists
                'needs_attention': [],
                'qawanted': [],
            }
    }
    """
    template = env.get_template(template.replace('templates/', '', 1))
    channel_info = {}
    for query_name, info in queries.items():
        channel_name = info['channel']
        channel_info[channel_name] = {
            'managers': [],
            'needs_attention': None,
            'qawanted': None,
        }
        
        # sift out the manager bugs that haven't had comment lately
        for manager_email in managers.keys():
            if managers[manager_email].has_key('nagging'):
                manager_name = managers[manager_email].get('name','no_name')
                if managers[manager_email]['nagging'].has_key(query_name):
                    manager_bugs = managers[manager_email]['nagging'][query_name].get('bugs')
                    channel_info[channel_name]['managers'].append({'name':manager_name,'bugs':manager_bugs})
                
        # filter out bugs that are unassigned
        unassigned_bugs = []
        for bug in info['bugs']:
            if bug.assigned_to.real_name != None and bug.assigned_to.real_name[:6] == 'Nobody':
                unassigned_bugs.append(bug)
        channel_info[channel_name]['managers'].append({'name':'Unassigned','bugs':unassigned_bugs})

        # TODO also check for 'qawanted', 'topcrash', 'startupcrash', 'relman-channel-meeting'

    return template.render(channel_info=channel_info, days_since_comment=days_since_comment)

def generateEmailOutput(queries, template, show_summary=False, show_comment=False, manager_email=None, 
                    cc_list=None):
    template_params = {}
    toaddrs = []   

    # stripping off the templates dir, just in case it gets passed in the args
    template = env.get_template(template.replace('templates/', '', 1))
    message_body = template.render(queries=template_params, show_summary=show_summary, show_comment=show_comment)

    for query,results in queries.items():
        template_params[query] = {'buglist': []}
        for bug in results['bugs']:
            template_params[query]['buglist'].append({
                    'id':bug.id,
                    'summary':bug.summary,
                    #'comment': bug.comments[-1].creation_time.replace(tzinfo=None),
                    'assignee': bug.assigned_to.real_name
            })
            # more hacking for JS special casing
            if bug.assigned_to.name == 'general@js.bugs' and 'dmandelin@mozilla.com' not in toaddrs:
                toaddrs.append('dmandelin@mozilla.com')
            if people.people_by_bzmail.has_key(bug.assigned_to.name):
                person = dict(people.people_by_bzmail[bug.assigned_to.name])
                if person['mozillaMail'] not in toaddrs:
                    toaddrs.append(person['mozillaMail'])
                    
    message_body = template.render(queries=template_params, show_summary=show_summary, show_comment=show_comment)
    # is our only email to a manager? then only cc the REPLY_TO_EMAIL
    manager = dict(people.people[manager_email])
    if len(toaddrs) == 1 and toaddrs[0] == manager_email or toaddrs[0] == manager.get('bugzillaMail'):
        if toaddrs[0] == 'dmandelin@mozilla.com':
            cc_list = [REPLY_TO_EMAIL, 'danderson@mozilla.com','nihsanullah@mozilla.com']
        else:
            cc_list = [REPLY_TO_EMAIL]
        print "Debug, not cc'ing a manager"
    else:
        if cc_list == None:
            if manager_email == 'dmandelin@mozilla.com':
                cc_list = [manager_email, REPLY_TO_EMAIL, 'danderson@mozilla.com', 'nihsanullah@mozilla.com']
            else:
                cc_list = [manager_email, REPLY_TO_EMAIL]
        # no need to send to as well as cc a manager
        for email in toaddrs:
            if email in cc_list:
                toaddrs.remove(email)
    message_subject = EMAIL_SUBJECT
    message = ("From: %s\r\n" % REPLY_TO_EMAIL
        + "To: %s\r\n" % ",".join(toaddrs)
        + "CC: %s\r\n" % ",".join(cc_list)
        + "Reply-To: %s\r\n" % REPLY_TO_EMAIL
        + "Subject: %s\r\n" % message_subject
        + "\r\n" 
        + message_body)
    toaddrs = toaddrs + cc_list

    return toaddrs,message


def sendMail(toaddrs,msg,username,password,dryrun=False):
    if dryrun:
        print "\n****************************\n* DRYRUN: not sending mail *\n****************************\n"
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
        wiki=False,
        show_summary=False,
        show_comment=False,
        email_cc_list=['release-mgmt@mozilla.com'],
        queries=[],
        days_since_comment=-1,
        verbose=False,
        keywords=None,
        )
    parser.add_argument("-d", "--dryrun", dest="dryrun", action="store_true",
            help="just do the query, and print emails to console without emailing anyone")
    parser.add_argument("-m", "--mozilla-email", dest="mozilla_mail",
            help="specify a specific address for sending email"),
    parser.add_argument("-p", "--email-password", dest="email_password",
            help="specify a specific password for sending email")
    parser.add_argument("-t", "--template", dest="template", required=True,
            help="template to use for the buglist output")
    parser.add_argument("-e", "--email-cc-list", dest="email_cc_list",
            action="append",
            help="email addresses to include in cc when sending mail")
    parser.add_argument("-q", "--query", dest="queries",
            action="append",
            help="a file containing a dictionary of a bugzilla query")
    parser.add_argument("-k", "--keyword", dest="keywords",
            action="append",
            help="keywords to collate buglists")
    parser.add_argument("--wiki", dest="wiki", action="store_true",
            help="flag to get wiki output to console instead of creating sendable emails")
    parser.add_argument("--show-summary", dest="show_summary", action="store_true",
            help="flag to ensure secure bug summaries don't go into output by accident, must explicitly ask to show")
    parser.add_argument("--show-comment", dest="show_comment", action="store_true",
            help="flag to display last comment on a bug in the message output")
    parser.add_argument("--days-since-comment", dest="days_since_comment",
            help="threshold to check comments against to take action based on days since comment")
    parser.add_argument("--verbose", dest="verbose", action="store_true",
            help="turn on verbose output")

    options, args = parser.parse_known_args()
    
    if options.queries == []:
        parser.error("Need to provide at least one query to run")
    
    if options.show_summary:
        print "\n *****ATTN***** Bug Summaries will be shown in output, be careful when sending emails.\n"

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
            collected_queries[query_name] = {
                'channel': info.get('query_channel', ''),
                'bugs' : [],
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
    manual_notify = []
    counter = 0

    def add_to_managers(manager_email, query):
        if managers[manager_email].has_key('nagging'):
            if managers[manager_email]['nagging'].has_key(query):
                managers[manager_email]['nagging'][query]['bugs'].append(bug)
                if options.verbose:
                    print "Adding %s to %s in nagging for %s" % (bug.id, query, manager_email)
            else:
                managers[manager_email]['nagging'][query] = { 'bugs': [bug] }
                if options.verbose:
                    print "Adding new query key %s for bug %s in nagging and %s" % (query, bug.id, manager_email)
        else:
            managers[manager_email]['nagging'] = {
                    query : { 'bugs': [bug] },
                }
            if options.verbose:
                print "Creating query key %s for bug %s in nagging and %s" % (query, bug.id, manager_email)
    
    for query in collected_queries.keys():
        for b in collected_queries[query]['bugs']:
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
                    # DEBUG 
                    # print "Nothing from assignee, using last comment %s" % bug.comments[-1].creation_time.replace(tzinfo=None)
                    last_comment = bug.comments[-1].creation_time.replace(tzinfo=None)
                if last_comment != None:
                    timedelta = datetime.now() - last_comment
                    if timedelta.days <= int(options.days_since_comment):
                        if options.verbose:
                            print "Skipping bug %s since it's had an assignee or manager comment within the past %s days" % (bug.id, options.days_since_comment)
                        send_mail = False
                        counter = counter - 1
                        manual_notify.remove(bug)
                    else:
                        if options.verbose:
                            print "This bug needs notification, it's been %s since last comment of note" % timedelta.days
    
            if send_mail:
                if 'nobody' in assignee:
                    if options.verbose:
                        print "No one assigned to: %s, adding to manual notification list..." % bug.id
                    assignee = None
                # TODO - get rid of this, SUCH A HACK!
                elif 'general@js.bugs' in assignee:
                    if options.verbose:
                        print "No one assigned to JS bug: %s, adding to dmandelin's list..." % bug.id
                    add_to_managers('dmandelin@mozilla.com', query)
                else:
                    if bug.assigned_to.real_name != None:
                        if person != None:
                            # check if assignee is already a manager, add to their own list
                            if managers.has_key(person['mozillaMail']):
                                add_to_managers(person['mozillaMail'], query)
                            # otherwise we search for the assignee's manager
                            else:
                                # check for manager key first, a few people don't have them
                                if person.has_key('manager') and person['manager'] != None:
                                    manager_email = person['manager']['dn'].split('mail=')[1].split(',')[0]
                                    if managers.has_key(manager_email):
                                        add_to_managers(manager_email, query)
                                    elif people.vices.has_key(manager_email):
                                        # we're already at the highest level we'll go
                                        if managers.has_key(assignee):
                                            add_to_managers(assignee, query)
                                        else:
                                            if options.verbose:
                                                print "%s has a V-level for a manager, and is not in the manager list" % assignee
                                            managers[person['mozillaMail']] = {}
                                            add_to_managers(person['mozillaMail'], query)
                                    else:
                                        # try to go up one level and see if we find a manager
                                        if people.people.has_key(manager_email):
                                            person = dict(people.people[manager_email])
                                            manager_email = person['manager']['dn'].split('mail=')[1].split(',')[0]
                                            if managers.has_key(manager_email):
                                                add_to_managers(manager_email, query)
                                        else:
                                            print "Manager could not be found: %s" % manager_email
                                else:
                                    print "%s's entry doesn't list a manager! Let's ask them to update phonebook." % person['name']

    if options.wiki:
        msg = generateWikiOutput(
            queries=collected_queries,
            template=options.template,
            managers=managers,
            keywords=options.keywords,
            days_since_comment=options.days_since_comment)
        print msg
    else:
        # Get yr nag on!
        for email, info in managers.items():
            if info.has_key('nagging'):
                toaddrs,msg = generateEmailOutput(
                    manager_email=email,
                    queries=info['nagging'],
                    template=options.template,
                    show_summary=options.show_summary,
                    show_comment=options.show_comment)
                while True:
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
    
                if inp == 'y' or inp == 'Y':
                    if options.email_password == None or options.mozilla_mail == None:
                        print "Please supply a username/password (-u, -p) for sending email"
                        sys.exit(1)
                    print "SENDING EMAIL"
                    sendMail(toaddrs,msg,options.mozilla_mail,options.email_password,options.dryrun)
                    sent_bugs = 0
                    for query, info in info['nagging'].items():
                        sent_bugs += len(info['bugs'])
                        # take sent bugs out of manual notification list
                        for bug in info['bugs']:
                            manual_notify.remove(bug)
                    counter = counter - sent_bugs
    
        # output the manual notification list
        print "\n*************\nNo email generated for %s/%s bugs, you will need to manually notify the following %s bugs:\n" % (counter, total_bugs, len(manual_notify))
        url = "https://bugzilla.mozilla.org/buglist.cgi?quicksearch="
        for bug in manual_notify:
            print "[Bug %s] -- assigned to: %s\n -- Last commented on: %s\n" % (bug.id, bug.assigned_to.real_name, bug.comments[-1].creation_time.replace(tzinfo=None))
            url += "%s," % bug.id
        print "Url for manual notification bug list: %s" % url
    
