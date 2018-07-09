# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from jinja2 import Environment, FileSystemLoader
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
from auto_nag.scripts.common import get_login_info, send_email
from auto_nag.bugzilla.utils import getVersions


release_version, beta_version, nightly_version = getVersions()


# https://bugzilla.mozilla.org/buglist.cgi?f1=cf_status_firefox62&f2=cf_status_firefox61&keywords=regression%2C%20&keywords_type=nowords&o1=anyexact&o2=equals&query_format=advanced&resolution=---&v1=affected%2C%20fixed&v2=unaffected&columnlist=product%2Ccomponent%2Cassigned_to%2Cbug_status%2Cresolution%2Cshort_desc%2Cchangeddate%2Ccf_status_firefox59%2Ccf_status_firefox60%2Ccf_status_firefox61%2Ccf_status_firefox62%2Ccf_status_firefox63&list_id=14223570
def get_bz_params():
    fields = ['id']
    params = {'include_fields': fields,
              'keywords': 'regression',
              'keywords_type': 'nowords',
              # not affecting release
              'f1': 'cf_status_firefox' + release_version,
              'o1': 'anyexact',
              'v1': 'unaffected',
              'f2': 'OP',
              'j2': 'OR',
              # affected in beta
              'f3': 'cf_status_firefox' + beta_version,
              'o3': 'anyexact',
              'v3': ['fixed', 'verified'],
              # affected in nightly
              'f4': 'cf_status_firefox' + nightly_version,
              'o4': 'anyexact',
              'v4': ['fixed', 'verified'],
              'f5': 'CP'

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
        print(date)
        title = title.format(date)
        return title, body
    return None, None


if __name__ == '__main__':
    description = 'Bug not affecting the release but affecting beta or nightly without the regression keyword',
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
    template = 'unaffected-affected-no-reg.html'
    subject = '[autonag] Bug not affecting the release but affecting beta or nightly without the regression keyword {}'
    title, body = get_email(login_info['bz_api_key'], date, template, subject)

    send_email(category="UNAFFECTED_AFFECTED_NO_REG", date=date, template=template, title=title, body=body, dryrun=args.dryrun)
