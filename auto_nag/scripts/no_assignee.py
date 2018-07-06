# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from dateutil.relativedelta import relativedelta
import functools
from jinja2 import Environment, FileSystemLoader
import json
from libmozdata.bugzilla import Bugzilla
from libmozdata.connection import Query
from libmozdata import hgmozilla, utils as lmdutils
from auto_nag.bugzilla.utils import get_config_path
from auto_nag import mail, utils
from auto_nag.scripts.common import get_login_info


def get_bz_params(date, bug_ids=[]):
    date = lmdutils.get_date_ymd(date)
    lookup = utils.get_config('no_assignee', 'days_lookup', 7)
    reporters = utils.get_config('no_assignee', 'reporter_exception', [])
    reporters = ','.join(reporters)
    start_date = date - relativedelta(days=lookup)
    end_date = date + relativedelta(days=1)
    fields = ['id']
    regexp = 'http[s]?://hg\.mozilla\.org/(releases/)?mozilla-[^/]+/rev/[0-9a-f]+' # NOQA
    params = {'include_fields': fields,
              'bug_id': bug_ids,
              'resolution': 'FIXED',
              'bug_status': ['RESOLVED', 'VERIFIED'],
              'f1': 'assigned_to',
              'o1': 'equals',
              'v1': 'nobody@mozilla.org',
              'f2': 'longdesc',
              'o2': 'regexp',
              'v2': regexp,
              'f3': 'resolution',
              'o3': 'changedafter',
              'v3': start_date,
              'f4': 'resolution',
              'o4': 'changedbefore',
              'v4': end_date}
    if reporters:
        params.update({'f5': 'reporter',
                       'o5': 'nowordssubstr',
                       'v5': reporters})

    return params


def get_revisions(bugids):
    """Get the revisions from the hg.m.o urls in the bug comments"""
    nightly_pats = Bugzilla.get_landing_patterns(channels=['nightly'])

    def comment_handler(bug, bugid, data):
        r = Bugzilla.get_landing_comments(bug['comments'], [], nightly_pats)
        data[bugid] = [i['revision'] for i in r]

    revisions = {}
    Bugzilla(bugids=bugids,
             commenthandler=comment_handler,
             commentdata=revisions,
             comment_include_fields=['text']).get_data().wait()

    return revisions


def filter_from_hg(revisions):
    """Get the bugs where an associated revision contains
       the bug id in the description"""

    def handler_rev(bugid, json, data):
        if bugid in json['desc']:
            data.add(int(bugid))

    url = hgmozilla.Revision.get_url('nightly')
    data = set()
    queries = []
    for bugid, rev in revisions.items():
        queries.append(Query(url, {'node': rev},
                             functools.partial(handler_rev,
                                               bugid), data))

    if queries:
        hgmozilla.Revision(queries=queries).wait()

    return list(sorted(data))


def get_bugs(date='today', bug_ids=[]):
    # the search query can be long to evaluate
    TIMEOUT = 240

    def bug_handler(bug, data):
        data.append(bug['id'])

    bugids = []
    Bugzilla(get_bz_params(date, bug_ids=bug_ids),
             bughandler=bug_handler,
             bugdata=bugids,
             timeout=TIMEOUT).get_data().wait()

    return bugids


def get_nobody(date='today', bug_ids=[]):
    bugids = get_bugs(date=date, bug_ids=bug_ids)
    revisions = get_revisions(bugids)
    bugids = filter_from_hg(revisions)

    return bugids


def get_email(bztoken, date, bug_ids=[]):
    Bugzilla.TOKEN = bztoken
    bugids = get_nobody(date, bug_ids=bug_ids)
    if bugids:
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('no_assignee_email.html')
        body = template.render(date=date,
                               bugids=bugids)

        title = '[autonag] Bugs with no assignees for the {}'.format(date)
        return title, body
    return None, None


def send_email(date='today', dryrun=False):
    login_info = get_login_info()
    date = lmdutils.get_date(date)
    title, body = get_email(login_info['bz_api_key'], date)
    if title:
        mail.send(login_info['ldap_username'],
                  utils.get_config('no_assignee', 'receivers', ['sylvestre@mozilla.com']),
                  title, body,
                  html=True, login=login_info, dryrun=dryrun)
    else:
        print('NO-ASSIGNEE: No data for {}'.format(date))


if __name__ == '__main__':
    description = 'Get bugs with no assignees and a patch which landed in m-c'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-d', '--dryrun', dest='dryrun',
                        action='store_true', default=False,
                        help='Just do the query, and print emails to console without emailing anyone') # NOQA
    parser.add_argument('-D', '--date', dest='date',
                        action='store', default='today',
                        help='Date for the query')
    args = parser.parse_args()
    send_email(date=args.date, dryrun=args.dryrun)
