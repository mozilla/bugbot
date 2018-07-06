# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from dateutil.relativedelta import relativedelta
from jinja2 import Environment, FileSystemLoader
import json
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
from auto_nag.bugzilla.utils import get_config_path
from auto_nag import mail, utils
from auto_nag.scripts.common import get_login_info


def get_bz_params(date):
    date = lmdutils.get_date_ymd(date)
    lookup = utils.get_config('common', 'days_lookup', 7)
    start_date = date - relativedelta(days=lookup)
    end_date = date + relativedelta(days=1)
    fields = ['id']
    params = {'include_fields': fields,
              'bug_status': ['RESOLVED', 'VERIFIED', 'CLOSED'],
              'f1': 'keywords',
              'o1': 'casesubstring',
              'v1': 'leave-open',
              'f2': 'resolution',
              'o2': 'changedafter',
              'v2': start_date,
              'f3': 'resolution',
              'o3': 'changedbefore',
              'v3': end_date}

    return params


def get_bugs(date='today'):
    # the search query can be long to evaluate
    TIMEOUT = 240

    def bug_handler(bug, data):
        data.append(bug['id'])

    bugids = []
    Bugzilla(get_bz_params(date),
             bughandler=bug_handler,
             bugdata=bugids,
             timeout=TIMEOUT).get_data().wait()

    return sorted(bugids)


def autofix(bugs):
    bugs = list(map(str, bugs))
    Bugzilla(bugs).put({
        'keywords': {
            'remove': ['leave-open']
            }
        })

    return bugs


def get_email(bztoken, date, dryrun):
    Bugzilla.TOKEN = bztoken
    bugids = get_bugs(date=date)
    if not dryrun:
        bugids = autofix(bugids)
    if bugids:
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('leave_open_email.html')
        body = template.render(date=date,
                               bugids=bugids)
        title = '[autonag] Closed bugs with leave-open keyword for the {}'.format(date)
        return title, body
    return None, None


def send_email(date='today', dryrun=False):
    login_info = get_login_info()
    date = lmdutils.get_date(date)
    title, body = get_email(login_info['bz_api_key'], date, dryrun)
    if title:
        mail.send(login_info['ldap_username'],
                  utils.get_config('common', 'receivers', ['sylvestre@mozilla.com']),
                  title, body,
                  html=True, login=login_info, dryrun=dryrun)
    else:
        print('LEAVE-OPEN: No data for {}'.format(date))


if __name__ == '__main__':
    description = 'Get the closed bugs with leave-open keyword'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-d', '--dryrun', dest='dryrun',
                        action='store_true', default=False,
                        help='Just do the query, and print emails to console without emailing anyone') # NOQA
    parser.add_argument('-D', '--date', dest='date',
                        action='store', default='today',
                        help='Date for the query')
    args = parser.parse_args()
    send_email(date=args.date, dryrun=args.dryrun)
