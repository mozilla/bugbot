# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from jinja2 import Environment, FileSystemLoader
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
from auto_nag.scripts.common import get_login_info, send_email
from auto_nag.bugzilla.utils import getVersions


release_version, beta_version, central_version = getVersions()


# https://bugzilla.mozilla.org/buglist.cgi?o1=isempty&version=62%20Branch&short_desc_type=notregexp&f1=cf_status_firefox62&short_desc=.%2ARisk%20Assessment.%2A&resolution=---&query_format=advanced&product=Core&product=DevTools&product=Firefox&product=Firefox%20for%20Android&product=Testing&product=Toolkit&product=WebExtensions&list_id=14223824
def get_bz_params():
    fields = ['id']
    params = {'include_fields': fields,
              'resolution': ['---', 'FIXED'],
              'short_desc': '.*Risk Assessment.*',
              'short_desc_type': 'notregexp',
              'f1': 'cf_status_firefox' + beta_version,
              'o1': 'isempty',
              'product': ['Core', 'DevTools', 'Firefox', 'Firefox for Android', 'Testing', 'Toolkit', 'WebExtensions'],
              'version': beta_version + ' Branch'
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

def autofix(bugs):
    bugs = list(map(str, bugs))
    Bugzilla(bugs).put({
        'cf_status_firefox' + beta_version: ['affected']
    })
    return bugs

def get_email(bztoken, date, template, title, bug_ids=[], dryrun=True):
    Bugzilla.TOKEN = bztoken
    bugids = get_bugs()
#    if not dryrun:
#        bugids = autofix(bugids)
    if bugids:
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template(template)
        body = template.render(date=date,
                               bugids=bugids)
        print(date)
        title = title.format(date)
        return title, body
    return None, None


if __name__ == '__main__':
    description = 'Bug with Version set but not status_firefox',
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
    template = 'version_affected.html'
    subject = '[autonag] Bug with Version set but not status_firefox' + beta_version + ' {}'
    title, body = get_email(login_info['bz_api_key'], date, template, subject, dryrun=args.dryrun)

    send_email(category="VERSION_AFFECTED", date=date, template=template, title=title, body=body, dryrun=args.dryrun)
