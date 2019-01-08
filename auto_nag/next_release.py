# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from datetime import datetime
import dateutil.parser
from jinja2 import Environment, FileSystemLoader
import pytz
import re
import requests


_NEXT_RELEASE = None
TEMPLATE_PAT = re.compile(r'<p>(.*)</p>', re.DOTALL)


class NextReleaseError(Exception):
    def __init__(self):
        super(NextReleaseError, self).__init__()

    def send_mail(self, dryrun=False):
        from . import mail, utils

        login_info = utils.get_login_info()
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('next_release_email')
        message = template.render()
        common = env.get_template('common.html')
        body = common.render(message=message)
        mail.send(
            login_info['ldap_username'],
            utils.get_config('next-release', 'receivers'),
            '[autonag] Next release date is not up-to-date',
            body,
            html=True,
            login=login_info,
            dryrun=dryrun,
        )


def get_date():
    global _NEXT_RELEASE
    if _NEXT_RELEASE is None:
        url = 'https://wiki.mozilla.org/Template:NextReleaseDate'
        template_page = str(requests.get(url).text.encode('utf-8'))
        m = TEMPLATE_PAT.search(template_page)
        _NEXT_RELEASE = dateutil.parser.parse(m.group(1).strip())
        _NEXT_RELEASE = pytz.utc.localize(_NEXT_RELEASE)
        now = pytz.utc.localize(datetime.utcnow())
        # NEXT RELEASE must be in the future
        if _NEXT_RELEASE < now:
            raise NextReleaseError()
    return _NEXT_RELEASE


if __name__ == '__main__':
    try:
        get_date()
    except NextReleaseError as e:
        parser = argparse.ArgumentParser(description='Check if next release date is ok')
        parser.add_argument(
            '-d',
            '--dryrun',
            dest='dryrun',
            action='store_true',
            help='Just do the query, and print emails to console without emailing anyone',
        )
        args = parser.parse_args()
        e.send_mail(dryrun=args.dryrun)
