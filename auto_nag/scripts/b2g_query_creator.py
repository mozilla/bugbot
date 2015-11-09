#!/usr/bin/python

import datetime
import subprocess
import os
import json
from argparse import ArgumentParser

from auto_nag.bugzilla.utils import get_config_path, get_project_root_path


def createQuery(title, short_title, url, show_summary, cc, queries_dir):
    file_name = queries_dir + str(datetime.date.today()) + '_' + short_title
    if not os.path.exists(queries_dir):
        os.makedirs(queries_dir)
    qf = open(file_name, 'w')
    qf.write("query_name = \'" + title + "\'\n")
    qf.write("query_url = \'" + url + "\'\n")
    qf.write("show_summary = \'" + str(show_summary) + "\'\n")
    if cc is not None:
        qf.write("cc = \'" + ",".join(cc) + "\'\n")

    return file_name


def createQueriesList(print_all, queries_dir):
    queries = []
    weekday = datetime.datetime.today().weekday()
    for url in urls:
        try:
            cc = url[1][4]
        except IndexError:
            cc = None  # no cc
        # Every Weekday
        if weekday >= 0 and weekday < 5 and url[0] == 5:
            queries.append(createQuery(title=url[1][0], short_title=url[1][1],
                                       url=url[1][2], show_summary=url[1][3],
                                       cc=cc, queries_dir=queries_dir))
        # Monday only emails
        if weekday == 0 and url[0] == 0:
            queries.append(createQuery(title=url[1][0], short_title=url[1][1],
                                       url=url[1][2], show_summary=url[1][3],
                                       cc=cc, queries_dir=queries_dir))
        # Tuesday only emails
        if weekday == 1 and url[0] == 1:
            queries.append(createQuery(title=url[1][0], short_title=url[1][1],
                                       url=url[1][2], show_summary=url[1][3],
                                       cc=cc, queries_dir=queries_dir))
        # Thursday only emails
        if weekday == 3 and url[0] == 3:
            queries.append(createQuery(title=url[1][0], short_title=url[1][1],
                                       url=url[1][2], show_summary=url[1][3],
                                       cc=cc, queries_dir=queries_dir))
        # Friday only emails
        if weekday == 4 and url[0] == 4:
            queries.append(createQuery(title=url[1][0], short_title=url[1][1],
                                       url=url[1][2], show_summary=url[1][3],
                                       cc=cc, queries_dir=queries_dir))
    return queries

# ========================= CURRENT QUERIES ============================
# NOTE: You must replace query bug_status with comma-separated values
#    eg: &bug_status=UNCONFIRMED,NEW,ASSIGNED,REOPENED
#
# ==== KOI (v1.2) ====
unfixed_koi_sec_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_blocking_b2g&o1=equals&resolution=---&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&v1=koi%2B&f2=status_whiteboard&o2=notsubstring&v2=[no-nag]&o3=anywordssubstr&v3=Confidential%20Security&f3=bug_group"
unfixed_koi_url = "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_blocking_b2g&o1=equals&resolution=---&bug_status=UNCONFIRMED,NEW,READY,ASSIGNED,REOPENED&v1=koi%2B&f2=status_whiteboard&o2=notsubstring&v2=[no-nag]&o3=anywordssubstr&v3=Confidential%20Security&f3=bug_group&n3=1"

team_dev_koi_nom = "https://bugzilla.mozilla.org/buglist.cgi?f1=OP&f0=OP&o2=equals&f4=CP&j1=OR&f3=CP&f2=cf_blocking_b2g&bug_status=UNCONFIRMED,NEW,ASSIGNED,REOPENED&component=DOM%3A%20Device%20Interfaces&v2=koi%3F&product=Core&o5=equals&n5=1&v5=FIXED&f5=resolution"
team_dev_koi_blockers = "https://bugzilla.mozilla.org/buglist.cgi?f1=OP&f0=OP&o2=equals&f4=CP&j1=OR&f3=CP&f2=cf_blocking_b2g&bug_status=UNCONFIRMED,NEW,ASSIGNED,REOPENED&component=DOM%3A%20Device%20Interfaces&v2=koi%2B&product=Core&o5=equals&n5=1&v5=FIXED&f5=resolution&o6=equals&n6=1&v6=WORKSFORME&f6=resolution&o7=equals&n7=1&v7=DUPLICATE&f7=resolution&o8=equals&n8=1&v8=INVALID&f8=resolution&o9=equals&n9=1&v9=WONTFIX&f9=resolution"

team_gfx_koi_nom = "https://bugzilla.mozilla.org/buglist.cgi?f1=OP&f0=OP&o2=equals&f4=CP&j1=OR&f3=CP&f2=cf_blocking_b2g&bug_status=UNCONFIRMED,NEW,ASSIGNED,REOPENED&component=Graphics%3A%20Layers&v2=koi%3F&product=Core&o5=equals&n5=1&v5=FIXED&f5=resolution"
team_gfx_koi_blockers = "https://bugzilla.mozilla.org/buglist.cgi?f1=OP&f0=OP&o2=equals&f4=CP&j1=OR&f3=CP&f2=cf_blocking_b2g&bug_status=UNCONFIRMED,NEW,ASSIGNED,REOPENED&component=Graphics%3A%20Layers&v2=koi%2B&product=Core&o5=equals&n5=1&v5=FIXED&f5=resolution&o6=equals&n6=1&v6=WORKSFORME&f6=resolution&o7=equals&n7=1&v7=DUPLICATE&f7=resolution&o8=equals&n8=1&v8=INVALID&f8=resolution&o9=equals&n9=1&v9=WONTFIX&f9=resolution"

team_media_koi_nom = "https://bugzilla.mozilla.org/buglist.cgi?f1=OP&f0=OP&o2=equals&f4=CP&j1=OR&f3=CP&f2=cf_blocking_b2g&bug_status=UNCONFIRMED,NEW,ASSIGNED,REOPENED&component=Gaia%3A%3ACamera&component=Gaia%3A%3AFMRadio&component=Gaia%3A%3AMusic&component=Gaia%3A%3AVideo&v2=koi%3F&product=Firefox%20OS&o5=equals&n5=1&v5=FIXED&f5=resolution&o6=equals&n6=1&v6=WORKSFORME&f6=resolution&o7=equals&n7=1&v7=DUPLICATE&f7=resolution&o8=equals&n8=1&v8=INVALID&f8=resolution&o9=equals&n9=1&v9=WONTFIX&f9=resolution"
team_media_koi_blockers = "https://bugzilla.mozilla.org/buglist.cgi?f1=OP&f0=OP&o2=equals&f4=CP&j1=OR&f3=CP&f2=cf_blocking_b2g&bug_status=UNCONFIRMED,NEW,ASSIGNED,REOPENED&component=Gaia%3A%3ACamera&component=Gaia%3A%3AFMRadio&component=Gaia%3A%3AMusic&component=Gaia%3A%3AVideo&v2=koi%2B&product=Firefox%20OS&o5=equals&n5=1&v5=FIXED&f5=resolution&o6=equals&n6=1&v6=WORKSFORME&f6=resolution&o7=equals&n7=1&v7=DUPLICATE&f7=resolution&o8=equals&n8=1&v8=INVALID&f8=resolution&o9=equals&n9=1&v9=WONTFIX&f9=resolution"

team_comm_koi_nom = "https://bugzilla.mozilla.org/buglist.cgi?f1=OP&f0=OP&o2=equals&f4=CP&j1=OR&f3=CP&f2=cf_blocking_b2g&bug_status=UNCONFIRMED,NEW,ASSIGNED,REOPENED&component=Gaia%3A%3AContacts&component=Gaia%3A%3ADialer&component=Gaia%3A%3AEverything.me&component=Gaia%3A%3ASMS&v2=koi%3F&product=Firefox%20OS&o5=equals&n5=1&v5=FIXED&f5=resolution"
team_comm_koi_blockers = "https://bugzilla.mozilla.org/buglist.cgi?f1=OP&f0=OP&o2=equals&f4=CP&j1=OR&f3=CP&f2=cf_blocking_b2g&bug_status=UNCONFIRMED,NEW,ASSIGNED,REOPENED&component=Gaia%3A%3AContacts&component=Gaia%3A%3ADialer&component=Gaia%3A%3AEverything.me&component=Gaia%3A%3ASMS&v2=koi%2B&product=Firefox%20OS&o5=equals&n5=1&v5=FIXED&f5=resolution&o6=equals&n6=1&v6=WORKSFORME&f6=resolution&o7=equals&n7=1&v7=DUPLICATE&f7=resolution&o8=equals&n8=1&v8=INVALID&f8=resolution&o9=equals&n9=1&v9=WONTFIX&f9=resolution"

koi_regressions_unfixed = "https://bugzilla.mozilla.org/buglist.cgi?j_top=OR&keywords=regression%2C%20regressionwindow-wanted%2C%20&keywords_type=anywords&f1=cf_blocking_b2g&o1=anywords&bug_status=UNCONFIRMED&bug_status=NEW&bug_status=ASSIGNED&bug_status=REOPENED&v1=koi"
koi_assignee_no_comment_three_days = "https://bugzilla.mozilla.org/buglist.cgi?o5=nowordssubstr&f1=OP&f0=OP&f8=owner_idle_time&o2=equals&f4=OP&v5=fixed%20verified%20unaffected%20wontfix&j1=OR&f3=CP&f2=cf_blocking_b2g&bug_status=UNCONFIRMED&bug_status=NEW&bug_status=ASSIGNED&bug_status=REOPENED&j4=OR&f5=cf_status_b2g_1_2&v8=-3d&f6=CP&v2=koi%2B&f7=CP&o8=greaterthan"

# ==== General ====
needinfo_sec_blockers_url = "https://bugzilla.mozilla.org/buglist.cgi?o1=anywords&o2=substring&v1=koi%2B&v2=needinfo%3F&f1=cf_blocking_b2g&resolution=---&f2=flagtypes.name&f3=status_whiteboard&o3=notsubstring&v3=[no-nag]&o4=anywordssubstr&v4=Confidential%20Security&f4=bug_group"
needinfo_blockers_url = "https://bugzilla.mozilla.org/buglist.cgi?o1=anywords&o2=substring&v1=koi%2B&v2=needinfo%3F&f1=cf_blocking_b2g&resolution=---&f2=flagtypes.name&f3=status_whiteboard&o3=notsubstring&v3=[no-nag]&o4=anywordssubstr&v4=Confidential%20Security&f4=bug_group&n4=1"

# TODO - sort the queries according to a priority flag
# TODO - batch up by query name (so sec & non-sec get in the same output)
urls = [
    (5, ["Blocker Bugs with Need-Info? (Sec)", "needinfo_sec_blockers", needinfo_sec_blockers_url, 0]),
    (5, ["Blocker Bugs with Need-Info?", "needinfo_blockers", needinfo_blockers_url, 1]),
    (0, ["Bugs Blocking KOI (Sec)", "unfixed_koi_sec", unfixed_koi_sec_url, 0]),
    (0, ["Bugs Blocking KOI", "unfixed_koi", unfixed_koi_url, 1]),
    (1, ["Koi Blocking Nominiations for DOM: Dev Interfaces", "team_dev_koi_nom", team_dev_koi_nom, 1, ["dhylands@mozilla.com", ]]),
    (1, ["Koi Blocker Bugs, DOM: Dev Interfaces", "team_dev_koi_blockers", team_dev_koi_blockers, 1, ["dhylands@mozilla.com", ]]),
    (1, ["Koi Blocking Nominiations for Graphics", "team_gfx_koi_nom", team_gfx_koi_nom, 1, ["msreckovic@mozilla.com", ]]),
    (1, ["Koi Blocker Bugs, Graphics", "team_gfx_koi_blockers", team_gfx_koi_blockers, 1, ["msreckovic@mozilla.com", ]]),
    (1, ["Koi Blocking Nominiations for B2G: Media", "team_media_koi_nom", team_media_koi_nom, 1, ["hkoka@mozilla.com", ]]),
    (1, ["Koi Blocker Bugs, B2G: Media", "team_media_koi_blockers", team_media_koi_blockers, 1, ["hkoka@mozilla.com", ]]),
    (1, ["Koi Blocking Nominiations for B2G: Communications", "team_comm_koi_nom", team_comm_koi_nom, 1, ["dscravaglieri@mozilla.com", ]]),
    (1, ["Koi Blocker Bugs, B2G: Communications", "team_comm_koi_blockers", team_comm_koi_blockers, 1, ["dscravaglieri@mozilla.com", ]]),
    (4, ["Koi Blocker Bugs, No Comment from Assignee in 3 days or more", "koi_assignee_no_comment_three_days", koi_assignee_no_comment_three_days, 1]),
    (4, ["Koi Blocker Bugs, Regressions", "koi_regressions_unfixed", koi_regressions_unfixed, 1]),
]


def cleanUp(queries_dir):
    try:
        for file in os.listdir(queries_dir):
            os.remove(os.path.join(queries_dir, file))
        return True
    except Exception as error:
        print 'Error: ', error
        return False
if __name__ == '__main__':
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
    queries = createQueriesList(print_all=options.queries_only,
                                queries_dir=queries_dir)

    if options.queries_only:
        for url in urls:
            print url
    else:
        command = [
            scripts_dir + "email_nag.py",
            "-t", "daily_b2g_email",
            "--no-verification",
            "-m", config['ldap_username'],
            "-p", config['ldap_password']]
        for query in queries:
            command.append('-q')
            command.append(query)
        if ('-r') in args:
            subject = datetime.datetime.today().strftime("%A %b %d") + " -- Daily B2G Drivers Rollup"
            command.extend(['-e', 'b2g-release-drivers@mozilla.org'])
        else:
            subject = datetime.datetime.today().strftime("%A %b %d") + " -- Daily B2G Blocking Bugs Alert"
        command.extend(['-s',  subject])
        # send all other args to email_nag script argparser
        command.extend(args)
        subprocess.call(command)
        cleanUp(queries_dir)
