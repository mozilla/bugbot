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
scripts_dir = os.getcwd() + "/scripts/"
queries_dir = os.getcwd() + "/queries/"


def getTemplateValue(url):
    version_regex = re.compile(".*<p>(.*)</p>.*")
    template_page = urllib2.urlopen(url).read().replace('\n', '')
    parsed_template = version_regex.match(template_page)
    return parsed_template.groups()[0]


def getReportURL(approval_flag, span):
    a = urllib2.urlopen("https://bugzilla.mozilla.org/page.cgi?id=release_tracking_report.html&q=" + approval_flag + "%3A%2B%3A" + span + "%3A0%3Aand%3A")
    return a.url

no_nag = ";field3-1-0=status_whiteboard;type3-1-0=notsubstring;value3-1-0=[no-nag]"
beta_version = getTemplateValue("https://wiki.mozilla.org/Template:BETA_VERSION")
aurora_version = getTemplateValue("https://wiki.mozilla.org/Template:AURORA_VERSION")
central_version = getTemplateValue("https://wiki.mozilla.org/Template:CENTRAL_VERSION")
esr_version = getTemplateValue("https://wiki.mozilla.org/Template:ESR_VERSION")
cycle_span = getTemplateValue("https://wiki.mozilla.org/Template:CURRENT_CYCLE")

unlanded_beta_url = getReportURL("approval-mozilla-beta", 	cycle_span) + ";field0-0-0=cf_status_firefox" + beta_version + ";type0-0-0=nowordssubstr;value0-0-0=unaffected,fixed,verified,wontfix,disabled" + ";field0-1-0=cf_tracking_firefox" + beta_version + ";type0-1-0=equals;value0-1-0=%2B;field0-2-0=status_whiteboard;type0-2-0=notsubstring;value0-2-0=[no-nag]"
unlanded_aurora_url = getReportURL("approval-mozilla-aurora", cycle_span) + ";field0-0-0=cf_status_firefox" + aurora_version + ";type0-0-0=nowordssubstr;value0-0-0=unaffected,fixed,verified,wontfix,disabled" + ";field0-1-0=cf_tracking_firefox" + aurora_version + ";type0-1-0=equals;value0-1-0=%2B;field0-2-0=status_whiteboard;type0-2-0=notsubstring;value0-2-0=[no-nag]"
unlanded_esr38_url = getReportURL("approval-mozilla-esr38", cycle_span) + ";field0-0-0=cf_status_firefox_esr" + esr_version + ";type0-0-0=nowordssubstr;value0-0-0=unaffected,fixed,verified,wontfix,disabled" + ";field0-1-0=cf_tracking_firefox_esr" + esr_version + ";type0-1-0=equals;value0-1-0=%2B;field0-2-0=status_whiteboard;type0-2-0=notsubstring;value0-2-0=[no-nag]"

tracking_beta_url = "https://bugzilla.mozilla.org/buglist.cgi?type1-0-0=equals;type0-1-0=notequals;type0-5-0=notequals;value0-5-0=disabled;value0-4-0=verified;field0-1-0=cf_status_firefox" + beta_version + ";field0-0-0=cf_tracking_firefox" + beta_version + ";field2-0-0=flagtypes.name;value0-3-0=unaffected;value0-6-0=verified%20disabled;value0-1-0=wontfix;field0-5-0=cf_status_firefox" + beta_version + ";type0-0-0=equals;value0-0-0=%2B;type0-2-0=notequals;negate1=1;field0-3-0=cf_status_firefox" + beta_version + ";type0-4-0=notequals;value2-0-0=approval-mozilla-beta%3F;field0-6-0=cf_status_firefox" + beta_version + ";type2-0-0=notsubstring;value0-2-0=fixed;type0-3-0=notequals;value1-0-0=core-security;field0-2-0=cf_status_firefox" + beta_version + ";field0-4-0=cf_status_firefox" + beta_version + ";type0-6-0=notequals;field1-0-0=bug_group;field2-1-0=status_whiteboard;type2-1-0=notsubstring;value2-1-0=[no-nag]"

tracking_aurora_url = "https://bugzilla.mozilla.org/buglist.cgi?type1-0-0=equals;type0-1-0=notequals;type0-5-0=notequals;value0-5-0=disabled;value0-4-0=verified;type3-0-0=notequals;field0-1-0=cf_status_firefox" + aurora_version + ";field0-0-0=cf_tracking_firefox" + aurora_version + ";field2-0-0=flagtypes.name;value0-3-0=unaffected;value0-6-0=verified%20disabled;value0-1-0=wontfix;field0-5-0=cf_status_firefox" + aurora_version + ";type0-0-0=equals;value0-0-0=%2B;type0-2-0=notequals;negate1=1;field0-3-0=cf_status_firefox" + aurora_version + ";type0-4-0=notequals;value3-0-0=%2B;value2-0-0=approval-mozilla-aurora%3F;field0-6-0=cf_status_firefox" + aurora_version + ";field3-0-0=cf_tracking_firefox" + beta_version + ";type2-0-0=notsubstring;value0-2-0=fixed;type0-3-0=notequals;value1-0-0=core-security;field0-2-0=cf_status_firefox" + aurora_version + ";field0-4-0=cf_status_firefox" + aurora_version + ";type0-6-0=notequals;field1-0-0=bug_group;field2-1-0=status_whiteboard;type2-1-0=notsubstring;value2-1-0=[no-nag]"

tracking_central_url = "https://bugzilla.mozilla.org/buglist.cgi?negate1=1;field0-3-0=cf_status_firefox" + central_version + ";value3-1-0=%2B;type1-0-0=equals;type0-1-0=notequals;type0-5-0=notequals;value0-5-0=disabled;value0-4-0=verified;type3-0-0=notequals;field0-1-0=cf_status_firefox" + central_version + ";field0-0-0=cf_tracking_firefox" + central_version + ";type0-4-0=notequals;value3-0-0=%2B;value2-0-0=approval-mozilla-aurora%3F;field2-0-0=flagtypes.name;field3-1-0=cf_tracking_firefox" + aurora_version + ";field0-6-0=cf_status_firefox" + central_version + ";value0-3-0=unaffected;field3-0-0=cf_tracking_firefox" + beta_version + ";type2-0-0=notsubstring;value0-2-0=fixed;value0-6-0=verified%20disabled;value0-1-0=wontfix;type0-3-0=notequals;value1-0-0=core-security;field0-2-0=cf_status_firefox" + central_version + ";type3-1-0=notequals;field0-5-0=cf_status_firefox" + central_version + ";field0-4-0=cf_status_firefox" + central_version + ";type0-6-0=notequals;type0-0-0=equals;value0-0-0=%2B;type0-2-0=notequals;field1-0-0=bug_group;field2-1-0=status_whiteboard;type2-1-0=notsubstring;value2-1-0=[no-nag]"

tracking_beta_touch_url = "https://bugzilla.mozilla.org/buglist.cgi?negate1=1;field0-3-0=cf_status_firefox" + beta_version + ";type1-0-0=equals;type0-1-0=notequals;type0-5-0=notequals;value0-5-0=disabled;value0-4-0=verified;type3-0-0=greaterthan;field0-1-0=cf_status_firefox" + beta_version + ";field0-0-0=cf_tracking_firefox" + beta_version + ";type0-4-0=notequals;value3-0-0=3;value2-0-0=approval-mozilla-beta%3F;field2-0-0=flagtypes.name;field0-6-0=cf_status_firefox" + beta_version + ";value0-3-0=unaffected;field3-0-0=days_elapsed;type2-0-0=notsubstring;value0-2-0=fixed;value0-6-0=verified%20disabled;value0-1-0=wontfix;type0-3-0=notequals;value1-0-0=core-security;field0-2-0=cf_status_firefox" + beta_version + ";field0-5-0=cf_status_firefox" + beta_version + ";field0-4-0=cf_status_firefox" + beta_version + ";type0-6-0=notequals;type0-0-0=equals;value0-0-0=%2B;type0-2-0=notequals;field1-0-0=bug_group" + no_nag

tracking_aurora_touch_url = "https://bugzilla.mozilla.org/buglist.cgi?negate1=1;field0-3-0=cf_status_firefox" + aurora_version + ";type4-0-0=greaterthan;type1-0-0=equals;type0-1-0=notequals;type0-5-0=notequals;value0-5-0=disabled;value0-4-0=verified;type3-0-0=notequals;field0-1-0=cf_status_firefox" + aurora_version + ";field0-0-0=cf_tracking_firefox" + aurora_version + ";type0-4-0=notequals;value3-0-0=%2B;field4-0-0=days_elapsed;value2-0-0=approval-mozilla-aurora%3F;field2-0-0=flagtypes.name;field0-6-0=cf_status_firefox" + aurora_version + ";value0-3-0=unaffected;field3-0-0=cf_tracking_firefox" + beta_version + ";type2-0-0=notsubstring;value0-2-0=fixed;value0-6-0=verified%20disabled;value0-1-0=wontfix;type0-3-0=notequals;value1-0-0=core-security;field0-2-0=cf_status_firefox" + aurora_version + ";field0-5-0=cf_status_firefox" + aurora_version + ";value4-0-0=3;field0-4-0=cf_status_firefox" + aurora_version + ";type0-6-0=notequals;type0-0-0=equals;value0-0-0=%2B;type0-2-0=notequals;field1-0-0=bug_group" + no_nag

tracking_central_touch_url = "https://bugzilla.mozilla.org/buglist.cgi?negate1=1;field0-3-0=cf_status_firefox" + central_version + ";type1-0-0=equals;type2-1-0=notequals;type0-1-0=notequals;type0-5-0=notequals;value0-5-0=disabled;value0-4-0=verified;type3-0-0=greaterthan;field0-1-0=cf_status_firefox" + central_version + ";field0-0-0=cf_tracking_firefox" + central_version + ";type0-4-0=notequals;value3-0-0=3;value2-0-0=%2B;field2-0-0=cf_tracking_firefox" + beta_version + ";field0-6-0=cf_status_firefox" + central_version + ";value0-3-0=unaffected;field3-0-0=days_elapsed;type2-0-0=notequals;value0-2-0=fixed;value0-6-0=verified%" + central_version + "disabled;value0-1-0=wontfix;type0-3-0=notequals;value2-1-0=%2B;value1-0-0=core-security;field0-2-0=cf_status_firefox" + central_version + ";field0-5-0=cf_status_firefox" + central_version + ";field0-4-0=cf_status_firefox" + central_version + ";type0-6-0=notequals;type0-0-0=equals;value0-0-0=%2B;field2-1-0=cf_tracking_firefox" + aurora_version + ";type0-2-0=notequals;field1-0-0=bug_group" + no_nag

tracking_esr38_url = "https://bugzilla.mozilla.org/buglist.cgi?type0-1-0=nowordssubstr;field0-1-0=cf_status_firefox_esr" + esr_version + ";field0-0-0=cf_tracking_firefox_esr" + esr_version + ";value0-1-0=fixed%20verified%20disabled%20wontfix%20unaffected;type0-0-0=equals;value0-0-0=" + beta_version + "%2B;field0-2-0=status_whiteboard;type0-2-0=notsubstring;value0-2-0=[no-nag]"

needinfo_beta_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_tracking_firefox" + beta_version + "&v6=fixed%2Cwontfix%2Cunaffected%2Cverified%2Cdisabled&o1=anywords&resolution=---&o6=anywords&f12=flagtypes.name&v12=needinfo%3F&f11=OP&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&o12=equals&v1=%2B%2C%3F&f6=cf_status_firefox" + beta_version + "&n6=1"

needinfo_aurora_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_tracking_firefox" + aurora_version + "&v6=fixed%2Cwontfix%2Cunaffected%2Cverified%2Cdisabled&o1=anywords&resolution=---&o6=anywords&f12=flagtypes.name&v12=needinfo%3F&f11=OP&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&o12=equals&v1=%2B%2C%3F&f6=cf_status_firefox" + aurora_version + "&n6=1"

needinfo_central_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_tracking_firefox" + central_version + "&v6=fixed%2Cwontfix%2Cunaffected%2Cverified%2Cdisabled&o1=anywords&resolution=---&o6=anywords&f12=flagtypes.name&v12=needinfo%3F&f11=OP&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&o12=equals&v1=%2B%2C%3F&f6=cf_status_firefox" + central_version + "&n6=1"

needinfo_esr38_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_tracking_firefox_esr" + esr_version + "&v6=fixed%2Cwontfix%2Cunaffected%2Cverified%2Cdisabled&o1=anywords&resolution=---&o6=anywords&f12=flagtypes.name&v12=needinfo%3F&f11=OP&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&o12=equals&v1=%2B%2C%3F&f6=cf_status_firefox_esr" + esr_version + "&n6=1"

# TODO - sort the queries according to a priority flag
# TODO - separate queries for sec bugs, for now hide summary
# TODO - fix the 'untouched' queries

# tracked beta/aurora/nightly nobodies: https://bugzilla.mozilla.org/buglist.cgi?j_top=OR&f1=cf_tracking_firefox25&o3=equals&v3=%2B&o1=equals&emailtype1=exact&o2=equals&emailassigned_to1=1&f3=cf_tracking_firefox27&f2=cf_tracking_firefox26&bug_status=UNCONFIRMED&bug_status=NEW&bug_status=ASSIGNED&bug_status=REOPENED&email1=nobody%40mozilla.org&v1=%2B&v2=%2B
# need same but for untouched

urls = [
    (5, ["Unlanded Beta " + beta_version + " Bugs", "unlanded_beta", unlanded_beta_url, 0]),
    (5, ["Unlanded Aurora " + aurora_version + " Bugs", "unlanded_aurora", unlanded_aurora_url, 0]),
    (5, ["Unlanded ESR38 Bugs", "unlanded_esr38", unlanded_esr38_url, 0]),
    (5, ["Tracked or Nominated for Tracking with Need-Info? Beta " + beta_version + " Bugs", "needinfo_beta", needinfo_beta_url, 0]),
    (5, ["Tracked or Nominated for Tracking with Need-Info? Aurora " + aurora_version + " Bugs", "needinfo_aurora", needinfo_aurora_url, 0]),
    (5, ["Tracked or Nominated for Tracking with Need-Info? Nightly " + central_version + " Bugs", "needinfo_central", needinfo_central_url, 0]),
    (5, ["Tracked or Nominated for Tracking with Need-Info? ESR38 Bugs", "needinfo_esr38", needinfo_esr38_url, 0]),
    (0, ["Bugs Tracked for Beta " + beta_version, "tracking_beta", tracking_beta_url, 0]),
    (0, ["Bugs Tracked for Aurora " + aurora_version, "tracking_aurora", tracking_aurora_url, 0]),
    (0, ["Bugs Tracked for Nightly " + central_version, "tracking_central", tracking_central_url, 0]),
    (0, ["Bugs Tracked for ESR38", "tracking_esr38", tracking_esr38_url, 0]),
    (3, ["Tracked Beta " + beta_version + " Bugs, untouched this week", "untouched_tracking_beta", tracking_beta_touch_url, 0]),
    (3, ["Tracked Aurora " + aurora_version + " Bugs, untouched this week", "untouched_tracking_aurora", tracking_aurora_touch_url, 0]),
    (3, ["Tracked Nightly " + central_version + " Bugs, untouched this week", "untouched_tracking_nightly", tracking_central_touch_url, 0])
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
            queries.append(createQuery(title=url[1][0], short_title=url[1][1], url=url[1][2], show_summary=url[1][3]))
        if weekday == 0 and url[0] == 0:
            queries.append(createQuery(title=url[1][0], short_title=url[1][1], url=url[1][2], show_summary=url[1][3]))
        if weekday == 3 and url[0] == 3:
            queries.append(createQuery(title=url[1][0], short_title=url[1][1], url=url[1][2], show_summary=url[1][3]))
    print queries
    return queries


def cleanUp():
    for file in os.listdir(queries_dir):
        if file.startswith(str(datetime.date.today())):
            os.remove(os.path.join(queries_dir, file))

if __name__ == '__main__':
    parser = ArgumentParser(__doc__)
    parser.set_defaults(
        queries_only=False,
    )
    parser.add_argument("-q", "--queries-only", dest="queries_only", action="store_true",
                        help="just create and print queries")

    options, args = parser.parse_known_args()
    queries = createQueriesList(print_all=options.queries_only)
    if options.queries_only:
        for url in urls:
            print url
    else:
        command = [
            scripts_dir + "email_nag.py",
            "-t", "daily_email",
            "--no-verification",
            "-m", config['ldap_username'],
            "-p", config['ldap_password'],
            "-b", config['bz_api_key'],
            "-e", "release-mgmt@mozilla.com"]
        for query in queries:
            command.append('-q')
            command.append(query)
        subject = datetime.datetime.today().strftime("%A %b %d") + " -- Daily Release Tracking Alert"
        command.extend(['-s',  subject])
        # send all other args to email_nag script argparser
        command.extend(args)
        subprocess.call(command)
        cleanUp()
