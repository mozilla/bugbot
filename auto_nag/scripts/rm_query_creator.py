#!/usr/bin/python

import datetime
import subprocess
import json
from argparse import ArgumentParser
from auto_nag.bugzilla.utils import (get_config_path, get_project_root_path,
                                     createQueriesList, cleanUp, getVersions)

release_version, beta_version, central_version, esr_version = getVersions()

fixed_without_uplifts_url = ("https://bugzilla.mozilla.org/buglist.cgi?"
                             "query_format=advanced&"
                             "resolution=---&resolution=FIXED&"
                             # fixed or verified in central
                             "f1=cf_status_firefox" + central_version + "&o1=anyexact&v1=fixed,verified&"
                             "f2=OP&j2=OR&"
                             # affected in beta
                             "f3=cf_status_firefox" + beta_version + "&o3=equals&v3=affected&"
                             # or affected in release
                             "f4=cf_status_firefox" + release_version + "&o4=equals&v4=affected&"
                             "f5=CP"
                             )

# TODO - sort the queries according to a priority flag
# TODO - separate queries for sec bugs, for now hide summary
# TODO - fix the 'untouched' queries

urls = [
    (5, ["Notify release managers when bugs are marked fixed in nightly but still affected for beta or release", "fixed_without_uplifts", fixed_without_uplifts_url])
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
            print(url)
    else:
        command = [
            scripts_dir + "email_nag.py",
            "-t", "tracked_affected_email",
            "--no-verification",
            "-m", config['ldap_username'],
            "-p", config['ldap_password'],
            "-b", config['bz_api_key'],
            "-c",
            "-e", "release-mgmt@mozilla.com,tgrabowski@mozilla.com,yor@mozilla.com"]
        for query in queries:
            command.append('-q')
            command.append(query)
        subject = datetime.datetime.today().strftime("%A %b %d") + " -- Fixed in %s, Affecting %s or %s" % (central_version, beta_version, release_version)
        command.extend(['-s', subject])
        # send all other args to email_nag script argparser
        command.extend(args)
        subprocess.call(command)
        cleanUp(queries_dir)
