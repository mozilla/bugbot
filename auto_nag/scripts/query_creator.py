#!/usr/bin/python

import requests
import re
import datetime
import subprocess
import json
from argparse import ArgumentParser
from auto_nag.bugzilla.utils import (get_config_path, get_project_root_path,
                                     createQueriesList, cleanUp)
from urllib2 import urlopen
from auto_nag.common import getCurrentVersion


def getTemplateValue(url):
    version_regex = re.compile(".*<p>(.*)</p>.*")
    template_page = str(requests.get(url).text.encode('utf-8')).replace('\n', '')
    parsed_template = version_regex.match(template_page)
    return parsed_template.groups()[0]


def getReportURL(approval_flag, span):
    a = requests.get("https://bugzilla.mozilla.org/page.cgi?id=release_tracking_report.html&q=" + approval_flag + "%3A%2B%3A" + span + "%3A0%3Aand%3A")
    return a.url


no_nag = ";field3-1-0=status_whiteboard;type3-1-0=notsubstring;value3-1-0=[no-nag]"
versions = getCurrentVersion()
beta_version = versions['beta']
central_version = versions['central']
esr_version = versions['esr']

# TODO: We should have this in p-d at some point.
cycle_span = getTemplateValue("https://wiki.mozilla.org/Template:CURRENT_CYCLE")

unlanded_beta_url = getReportURL("approval-mozilla-beta", 	cycle_span) + ";field0-0-0=cf_status_firefox" + beta_version + ";type0-0-0=nowordssubstr;value0-0-0=unaffected,fixed,verified,wontfix,disabled" + ";field0-1-0=cf_tracking_firefox" + beta_version + ";type0-1-0=equals;value0-1-0=%2B;field0-2-0=status_whiteboard;type0-2-0=notsubstring;value0-2-0=[no-nag]"
unlanded_esr_url = getReportURL("approval-mozilla-esr" + esr_version, cycle_span) + ";field0-0-0=cf_status_firefox_esr" + esr_version + ";type0-0-0=nowordssubstr;value0-0-0=unaffected,fixed,verified,wontfix,disabled" + ";field0-1-0=cf_tracking_firefox_esr" + esr_version + ";type0-1-0=equals;value0-1-0=%2B;field0-2-0=status_whiteboard;type0-2-0=notsubstring;value0-2-0=[no-nag]"

tracking_beta_url = "https://bugzilla.mozilla.org/buglist.cgi?type1-0-0=equals;type0-1-0=notequals;type0-5-0=notequals;value0-5-0=disabled;value0-4-0=verified;field0-1-0=cf_status_firefox" + beta_version + ";field0-0-0=cf_tracking_firefox" + beta_version + ";field2-0-0=flagtypes.name;value0-3-0=unaffected;value0-6-0=verified%20disabled;value0-1-0=wontfix;field0-5-0=cf_status_firefox" + beta_version + ";type0-0-0=equals;value0-0-0=%2B;type0-2-0=notequals;negate1=1;field0-3-0=cf_status_firefox" + beta_version + ";type0-4-0=notequals;value2-0-0=approval-mozilla-beta%3F;field0-6-0=cf_status_firefox" + beta_version + ";type2-0-0=notsubstring;value0-2-0=fixed;type0-3-0=notequals;value1-0-0=core-security;field0-2-0=cf_status_firefox" + beta_version + ";field0-4-0=cf_status_firefox" + beta_version + ";type0-6-0=notequals;field1-0-0=bug_group;field2-1-0=status_whiteboard;type2-1-0=notsubstring;value2-1-0=[no-nag]"

tracking_central_url = "https://bugzilla.mozilla.org/buglist.cgi?negate1=1;field0-3-0=cf_status_firefox" + central_version + ";type1-0-0=equals;type0-1-0=notequals;type0-5-0=notequals;value0-5-0=disabled;value0-4-0=verified;type3-0-0=notequals;field0-1-0=cf_status_firefox" + central_version + ";field0-0-0=cf_tracking_firefox" + central_version + ";type0-4-0=notequals;value3-0-0=%2B;field0-6-0=cf_status_firefox" + central_version + ";value0-3-0=unaffected;field3-0-0=cf_tracking_firefox" + beta_version + ";value0-2-0=fixed;value0-6-0=verified%20disabled;value0-1-0=wontfix;type0-3-0=notequals;value1-0-0=core-security;field0-2-0=cf_status_firefox" + central_version + ";field0-5-0=cf_status_firefox" + central_version + ";field0-4-0=cf_status_firefox" + central_version + ";type0-6-0=notequals;type0-0-0=equals;value0-0-0=%2B;type0-2-0=notequals;field1-0-0=bug_group;field2-1-0=status_whiteboard;type2-1-0=notsubstring;value2-1-0=[no-nag]"

tracking_beta_touch_url = "https://bugzilla.mozilla.org/buglist.cgi?negate1=1;field0-3-0=cf_status_firefox" + beta_version + ";type1-0-0=equals;type0-1-0=notequals;type0-5-0=notequals;value0-5-0=disabled;value0-4-0=verified;type3-0-0=greaterthan;field0-1-0=cf_status_firefox" + beta_version + ";field0-0-0=cf_tracking_firefox" + beta_version + ";type0-4-0=notequals;value3-0-0=3;value2-0-0=approval-mozilla-beta%3F;field2-0-0=flagtypes.name;field0-6-0=cf_status_firefox" + beta_version + ";value0-3-0=unaffected;field3-0-0=days_elapsed;type2-0-0=notsubstring;value0-2-0=fixed;value0-6-0=verified%20disabled;value0-1-0=wontfix;type0-3-0=notequals;value1-0-0=core-security;field0-2-0=cf_status_firefox" + beta_version + ";field0-5-0=cf_status_firefox" + beta_version + ";field0-4-0=cf_status_firefox" + beta_version + ";type0-6-0=notequals;type0-0-0=equals;value0-0-0=%2B;type0-2-0=notequals;field1-0-0=bug_group" + no_nag

tracking_central_touch_url = "https://bugzilla.mozilla.org/buglist.cgi?negate1=1;field0-3-0=cf_status_firefox" + central_version + ";type1-0-0=equals;type0-1-0=notequals;type0-5-0=notequals;value0-5-0=disabled;value0-4-0=verified;type3-0-0=greaterthan;field0-1-0=cf_status_firefox" + central_version + ";field0-0-0=cf_tracking_firefox" + central_version + ";type0-4-0=notequals;value3-0-0=3;value2-0-0=%2B;field2-0-0=cf_tracking_firefox" + beta_version + ";field0-6-0=cf_status_firefox" + central_version + ";value0-3-0=unaffected;field3-0-0=days_elapsed;type2-0-0=notequals;value0-2-0=fixed;value0-6-0=verified%" + central_version + "disabled;value0-1-0=wontfix;type0-3-0=notequals;value1-0-0=core-security;field0-2-0=cf_status_firefox" + central_version + ";field0-5-0=cf_status_firefox" + central_version + ";field0-4-0=cf_status_firefox" + central_version + ";type0-6-0=notequals;type0-0-0=equals;value0-0-0=%2B;type0-2-0=notequals;field1-0-0=bug_group" + no_nag

tracking_esr_url = "https://bugzilla.mozilla.org/buglist.cgi?type0-1-0=nowordssubstr;field0-1-0=cf_status_firefox_esr" + esr_version + ";field0-0-0=cf_tracking_firefox_esr" + esr_version + ";value0-1-0=fixed%20verified%20disabled%20wontfix%20unaffected;type0-0-0=equals;value0-0-0=" + beta_version + "%2B;field0-2-0=status_whiteboard;type0-2-0=notsubstring;value0-2-0=[no-nag]"

needinfo_beta_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_tracking_firefox" + beta_version + "&v6=fixed%2Cwontfix%2Cunaffected%2Cverified%2Cdisabled&o1=anywords&resolution=---&o6=anywords&f12=flagtypes.name&v12=needinfo%3F&f11=OP&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&o12=equals&v1=%2B%2C%3F&f6=cf_status_firefox" + beta_version + "&n6=1"

needinfo_central_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_tracking_firefox" + central_version + "&v6=fixed%2Cwontfix%2Cunaffected%2Cverified%2Cdisabled&o1=anywords&resolution=---&o6=anywords&f12=flagtypes.name&v12=needinfo%3F&f11=OP&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&o12=equals&v1=%2B%2C%3F&f6=cf_status_firefox" + central_version + "&n6=1"

needinfo_esr_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_tracking_firefox_esr" + esr_version + "&v6=fixed%2Cwontfix%2Cunaffected%2Cverified%2Cdisabled&o1=anywords&resolution=---&o6=anywords&f12=flagtypes.name&v12=needinfo%3F&f11=OP&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&o12=equals&v1=%2B%2C%3F&f6=cf_status_firefox_esr" + esr_version + "&n6=1"

# TODO - sort the queries according to a priority flag
# TODO - separate queries for sec bugs, for now hide summary
# TODO - fix the 'untouched' queries

# tracked beta/nightly nobodies: https://bugzilla.mozilla.org/buglist.cgi?j_top=OR&f1=cf_tracking_firefox25&o3=equals&v3=%2B&o1=equals&emailtype1=exact&o2=equals&emailassigned_to1=1&f3=cf_tracking_firefox27&f2=cf_tracking_firefox26&bug_status=UNCONFIRMED&bug_status=NEW&bug_status=ASSIGNED&bug_status=REOPENED&email1=nobody%40mozilla.org&v1=%2B&v2=%2B
# need same but for untouched

urls = [
    (5, ["Unlanded Beta " + beta_version + " Bugs", "unlanded_beta", unlanded_beta_url]),
    (5, ["Unlanded ESR" + esr_version + " Bugs", "unlanded_esr", unlanded_esr_url]),
    (5, ["Tracked or Nominated for Tracking with Need-Info? Beta " + beta_version + " Bugs", "needinfo_beta", needinfo_beta_url]),
    (5, ["Tracked or Nominated for Tracking with Need-Info? Nightly " + central_version + " Bugs", "needinfo_central", needinfo_central_url]),
    (5, ["Tracked or Nominated for Tracking with Need-Info? ESR" + esr_version + " Bugs", "needinfo_esr", needinfo_esr_url]),
    (0, ["Bugs Tracked for Beta " + beta_version, "tracking_beta", tracking_beta_url]),
    (0, ["Bugs Tracked for Nightly " + central_version, "tracking_central", tracking_central_url]),
    (0, ["Bugs Tracked for ESR" + esr_version, "tracking_esr", tracking_esr_url]),
    (3, ["Tracked Beta " + beta_version + " Bugs, untouched this week", "untouched_tracking_beta", tracking_beta_touch_url]),
    (3, ["Tracked Nightly " + central_version + " Bugs, untouched this week", "untouched_tracking_nightly", tracking_central_touch_url])
]


if __name__ == '__main__':
    # basic setups
    CONFIG_JSON = get_config_path()
    config = json.load(open(CONFIG_JSON, 'r'))
    scripts_dir = get_project_root_path() + "auto_nag/scripts/"
    queries_dir = get_project_root_path() + "queries/"

    parser = ArgumentParser(__doc__)
    parser.set_defaults(
        queries_only=False,
    )
    parser.add_argument("-q", "--queries-only", dest="queries_only", action="store_true",
                        help="just create and print queries")

    options, args = parser.parse_known_args()
    weekday = datetime.datetime.today().weekday()
    queries = createQueriesList(queries_dir, weekday, urls, print_all=options.queries_only)
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
            "-e", "release-mgmt@mozilla.com,tgrabowski@mozilla.com,yor@mozilla.com"]
        for query in queries:
            command.append('-q')
            command.append(query)
        subject = datetime.datetime.today().strftime("%A %b %d") + " -- Daily Release Tracking Alert"
        command.extend(['-s',  subject])
        # send all other args to email_nag script argparser
        command.extend(args)
        subprocess.call(command)
        cleanUp(queries_dir)
