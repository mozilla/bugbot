# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from jinja2 import Environment, FileSystemLoader
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
from auto_nag.scripts.common import get_login_info, send_email


# https://bugzilla.mozilla.org/buglist.cgi?keywords=feature%2C%20regression%2C%20&keywords_type=allwords&resolution=---&resolution=FIXED&resolution=INVALID&resolution=WONTFIX&resolution=INACTIVE&resolution=DUPLICATE&resolution=WORKSFORME&resolution=INCOMPLETE&resolution=SUPPORT&resolution=EXPIRED&resolution=MOVED&query_format=advanced&list_id=14223560
def get_bz_params():
    fields = ['id']
    params = {'include_fields': fields,
              'resolution': ['---', 'FIXED'],
              'keywords': ['feature', 'regression'],
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
    template = 'feature_regression.html'
    subject = '[autonag] Bugs with feature and regression keywords {}'
    title, body = get_email(login_info['bz_api_key'], date, template, subject)

    send_email(category="FEATURE_REGRESSION", date=date, template=template, title=title, body=body, dryrun=args.dryrun)
