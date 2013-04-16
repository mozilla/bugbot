#!/usr/bin/python

import urllib2
import re
import datetime
import subprocess
import os
import json
from argparse import ArgumentParser

CONFIG_JSON = os.getcwd() + "/scripts/configs/config.json"
config = json.load(open(CONFIG_JSON, 'r'))
scripts_dir =  os.getcwd() + "/scripts/"
queries_dir =  os.getcwd() + "/queries/"

def getTemplateValue(url):
	version_regex = re.compile(".*<p>(.*)</p>.*")
	template_page = urllib2.urlopen(url).read().replace('\n', '')
	parsed_template = version_regex.match(template_page)
	return parsed_template.groups()[0]

def getReportURL(approval_flag, span):
	a = urllib2.urlopen("https://bugzilla.mozilla.org/page.cgi?id=release_tracking_report.html&q=" + approval_flag + "%3A%2B%3A" + span + "%3A0%3Aand%3A")
	return a.url
 
# From RyanVM   
# b2g tef+/shira+ bugs needing uplift to v1_0_1
# https://bugzilla.mozilla.org/buglist.cgi?order=Bug%20Number;bug_status=RESOLVED;bug_status=VERIFIED;resolution=FIXED;field0-0-0=cf_blocking_b2g;type0-0-0=anywordssubstr;value0-0-0=tef%2B%20shira%2B;field0-1-0=component;type0-1-0=nowords;value0-1-0=Gaia%20Server%20Security%20Payments%20Hardware%20Builds;field0-2-0=cf_last_resolved;type0-2-0=greaterthaneq;value0-2-0=2013-01-25;field0-3-0=cf_status_b2g18_1_0_1;type0-3-0=nowordssubstr;value0-3-0=fixed%20verified%20unaffected%20wontfix%20disabled;field0-4-0=status_whiteboard;type0-4-0=notsubstring;value0-4-0=NO_UPLIFT;

# b2g leo+ bugs needing uplift to b2g18
# https://bugzilla.mozilla.org/buglist.cgi?order=Bug%20Number;bug_status=RESOLVED;bug_status=VERIFIED;resolution=FIXED;field0-0-0=cf_blocking_b2g;type0-0-0=anywordssubstr;value0-0-0=leo%2B;field0-1-0=component;type0-1-0=nowords;value0-1-0=Gaia%20Server%20Security%20Payments%20Hardware%20Builds;field0-2-0=cf_last_resolved;type0-2-0=greaterthaneq;value0-2-0=2013-01-25;field0-3-0=cf_status_b2g18;type0-3-0=nowordssubstr;value0-3-0=fixed%20verified%20unaffected%20wontfix%20disabled;field0-4-0=status_whiteboard;type0-4-0=notsubstring;value0-4-0=NO_UPLIFT;

# b2g a+ needing uplift to b2g18
# https://bugzilla.mozilla.org/buglist.cgi?order=Bug%20Number;bug_status=RESOLVED;bug_status=VERIFIED;resolution=FIXED;field0-0-0=flagtypes.name;type0-0-0=equals;value0-0-0=approval-mozilla-b2g18%2B;field0-1-0=cf_status_b2g18;type0-1-0=nowordssubstr;value0-1-0=fixed%20verified%20unaffected%20wontfix%20disabled;


unfixed_tef_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_blocking_b2g&o1=equals&resolution=---&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&v1=tef%2B&f2=status_whiteboard&o2=notsubstring&v2=[no-nag]"
unfixed_leo_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_blocking_b2g&o1=equals&resolution=---&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&v1=leo%2B&f2=status_whiteboard&o2=notsubstring&v2=[no-nag]"
untouched_tef_url = unfixed_tef_url + "&o3=greaterthan&f3=owner_idle_time&v3=3"
untouched_leo_url = unfixed_leo_url + "&o3=greaterthan&f3=owner_idle_time&v3=3"
unlanded_tef_url = "https://bugzilla.mozilla.org/buglist.cgi?o5=nowords&v11=fixed%20verified%20unaffected%20wontfix%20disabled&j10=OR&o14=notsubstring&f13=OP&o2=anywordssubstr&v5=Gaia%20Server%20Security%20Payments%20Hardware%20Builds&f12=CP&j4=OR&f14=status_whiteboard&v2=tef%2B%20shira%2B&f10=OP&f1=OP&j13=OR&f8=cf_last_resolved&f0=OP&o11=nowordssubstr&f15=CP&resolution=FIXED&f9=CP&j7=OR&f4=OP&j1=OR&f3=CP&f2=cf_blocking_b2g&f11=cf_status_b2g18_1_0_1&bug_status=RESOLVED,VERIFIED&f5=component&v8=2013-01-25&v14=NO_UPLIFT&f6=CP&f7=OP&o8=greaterthaneq&f16=CP&f17=status_whiteboard&o17=notsubstring&v17=[no-nag]"
unlanded_leo_url = "https://bugzilla.mozilla.org/buglist.cgi?o5=nowords&v11=fixed%20verified%20unaffected%20wontfix%20disabled&j10=OR&o14=notsubstring&f13=OP&o2=anywordssubstr&v5=Gaia%20Server%20Security%20Payments%20Hardware%20Builds&f12=CP&j4=OR&f14=status_whiteboard&v2=leo%2B&f10=OP&f1=OP&j13=OR&f8=cf_last_resolved&f0=OP&o11=nowordssubstr&f15=CP&resolution=FIXED&f9=CP&j7=OR&f4=OP&j1=OR&f3=CP&f2=cf_blocking_b2g&f11=cf_status_b2g18&bug_status=RESOLVED,VERIFIED&f5=component&v8=2013-01-25&v14=NO_UPLIFT&f6=CP&f7=OP&o8=greaterthaneq&f16=CP&f17=status_whiteboard&o17=notsubstring&v17=[no-nag]"
needinfo_blockers_url = "https://bugzilla.mozilla.org/buglist.cgi?o1=anywords&o2=substring&v1=tef%2B%2Cleo%2B&v2=needinfo%3F&f1=cf_blocking_b2g&resolution=---&f2=flagtypes.name&f3=status_whiteboard&o3=notsubstring&v3=[no-nag]"

# TODO - sort the queries according to a priority flag
urls = [
    (5,["Unlanded TEF Bugs", "unlanded_tef", unlanded_tef_url, 1]),
    (5,["Unlanded LEO Bugs", "unlanded_leo", unlanded_leo_url, 1]),
    (5,["Blocker Bugs with Need-Info?", "needinfo_blockers", needinfo_blockers_url, 1]),
    (0,["Bugs Blocking TEF", "unfixed_tef", unfixed_tef_url, 1]),
    (0,["Bugs Blocking LEO", "unfixed_leo", unfixed_leo_url, 1]),
    (3,["TEF Blocker Bugs, untouched this week", "untouched_tef_blockers", untouched_tef_url, 1]),
    (3,["LEO Blocker Bugs, untouched this week", "untouched_leo_blockers", untouched_leo_url, 1]),
    ]

def createQuery(title, short_title, url, show_summary):
    file_name = queries_dir + str(datetime.date.today()) + '_' + short_title

    qf = open(file_name, 'w')
    qf.write("query_name = \'" + title + "\'\n")
    qf.write("query_url = \'" + url + "\'\n")
    qf.write("show_summary = \'" + str(show_summary) + "\'\n")

    return file_name 

def createQueriesList(print_all):
    queries = []
    weekday = datetime.datetime.today().weekday()
    for url in urls:
        if weekday >= 0 and weekday < 5 and url[0] == 5:
            queries.append(createQuery(title=url[1][0],short_title=url[1][1],url=url[1][2],show_summary=url[1][3]))
        if weekday == 0 and url[0] == 0:
            queries.append(createQuery(title=url[1][0],short_title=url[1][1],url=url[1][2],show_summary=url[1][3]))
        if weekday == 3 and url[0] == 3:
            queries.append(createQuery(title=url[1][0],short_title=url[1][1],url=url[1][2],show_summary=url[1][3]))
    print queries
    return queries

def cleanUp():
    for file in os.listdir(queries_dir):
        if file.startswith(str(datetime.date.today())):
            os.remove(os.path.join(queries_dir,file))

if __name__ == '__main__':
    parser = ArgumentParser(__doc__)
    parser.set_defaults(
        queries_only=False,
        dryrun=False,
        )
    parser.add_argument("-q", "--queries-only", dest="queries_only", action="store_true",
            help="just create and print queries")
    parser.add_argument("-d", "--dryrun", dest="dryrun", action="store_true",
            help="pass dryrun flag to the email_nag")

    options, args = parser.parse_known_args()
    
    queries = createQueriesList(print_all=options.queries_only)
    
    if options.queries_only:
        for url in urls:
            print url
    else:
        command = [
            scripts_dir + "email_nag.py",
            "-r", # rollup email, one per day
            "-t", "daily_b2g_email",
            "--no-verification",
            "-m", config['ldap_username'],
            "-p", config['ldap_password'],
            "-e", "jcheng@mozilla.com",
            "-e", "dietrich@mozilla.com",
            "-e", "ladamski@mozilla.com",
            "-e", "release-mgmt@mozilla.com"]
        if options.dryrun:
            command.append('-d')
        for query in queries:
            command.append('-q')
            command.append(query)
        subject = datetime.datetime.today().strftime("%A %b %d") + " -- Daily B2G Blocking Bugs Alert"
        command.extend(['-s',  subject])
        if options.dryrun:
            print "Command: %s" % command
        subprocess.call(command)
        if not options.dryrun:
            cleanUp()

