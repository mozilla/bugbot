# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from jinja2 import Environment, FileSystemLoader
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
from auto_nag import mail, utils
from auto_nag.scripts.common import get_login_info, send_email


# https://bugzilla.mozilla.org/buglist.cgi?keywords=topcrash%2C%20&keywords_type=allwords&bug_severity=major&bug_severity=normal&bug_severity=minor&bug_severity=trivial&bug_severity=enhancement&resolution=---&query_format=advanced
def get_bz_params():
    fields = ['id']
    params = {'include_fields': fields,
              'resolution': ['---'],
              "bug_severity": ["major", "normal", "minor", "trivial", "enhancement"],
              'keywords': 'topcrash',
              'keywords_type': 'allwords'
              }

    return params


def get_bugs():
    # the search query can be long to evaluate
    TIMEOUT = 240

    def bug_handler(bug, data):
        data.append(bug['id'])

    bugids = []
    Bugzilla(get_bz_params(),
             bughandler=bug_handler,
             bugdata=bugids,
             timeout=TIMEOUT).get_data().wait()

    return sorted(bugids)


def get_email(bztoken, date, template, title, bug_ids=[]):
    Bugzilla.TOKEN = bztoken
    bugids = get_bugs()
    if bugids:
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template(template)
        body = template.render(date=date,
                               bugids=bugids)
        title = title.format(date)
        return title, body
    return None, None


if __name__ == '__main__':
    description = 'Get the top crashes bug without a proper severity'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-d', '--dryrun', dest='dryrun',
                        action='store_true', default=False,
                        help='Just do the query, and print emails to console without emailing anyone') # NOQA
    parser.add_argument('-D', '--date', dest='date',
                        action='store', default='today',
                        help='Date for the query')
    args = parser.parse_args()

    login_info = get_login_info()
    date = lmdutils.get_date(args.date)
    template='topcrash_bad_severity.html'
    subject='[autonag] Bugs with topcrash keyword but incorrect severity {}'
    title, body = get_email(login_info['bz_api_key'], date, template, subject)

    send_email(category="TOPCRASH_BAD_SEVERITY", date=date, template=template , title=title, dryrun=args.dryrun)
