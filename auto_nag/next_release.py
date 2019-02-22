# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import dateutil.parser
from jinja2 import Environment, FileSystemLoader
from libmozdata import release_owners as ro, utils as lmdutils
import pytz
import re
import requests
from . import mail, utils


def send_mail(next_date, bad_date_nrd, bad_date_ro, dryrun=False):

    login_info = utils.get_login_info()
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('next_release_email')
    message = template.render(
        next_date=next_date, bad_date_nrd=bad_date_nrd, bad_date_ro=bad_date_ro
    )
    common = env.get_template('common.html')
    body = common.render(message=message, has_table=False)
    mail.send(
        login_info['ldap_username'],
        utils.get_config('next-release', 'receivers'),
        '[autonag] Next release date is not up-to-date',
        body,
        html=True,
        login=login_info,
        dryrun=dryrun,
    )


def check_dates(dryrun=False):
    next_date = utils.get_next_release_date()
    bad_date_nrd = bad_date_ro = None

    pat = re.compile(r'<p>(.*)</p>', re.DOTALL)
    url = 'https://wiki.mozilla.org/Template:NextReleaseDate'
    template_page = str(requests.get(url).text)
    m = pat.search(template_page)
    date = dateutil.parser.parse(m.group(1).strip())
    date = pytz.utc.localize(date)

    if date != next_date:
        bad_date_nrd = date.strftime('%Y-%m-%d')

    owners = ro.get_owners()
    now = lmdutils.get_date_ymd('today')
    for o in owners[::-1]:
        date = o['release date']
        if now < date:
            if date != next_date:
                bad_date_ro = date.strftime('%Y-%m-%d')
            break

    if bad_date_nrd or bad_date_ro:
        next_date = next_date.strftime('%Y-%m-%d')
        send_mail(next_date, bad_date_nrd, bad_date_ro, dryrun=dryrun)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check if next release date is ok')
    parser.add_argument(
        '-d',
        '--dryrun',
        dest='dryrun',
        action='store_true',
        help='Just do the query, and print emails to console without emailing anyone',
    )
    args = parser.parse_args()
    check_dates(dryrun=args.dryrun)
