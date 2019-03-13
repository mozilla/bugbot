# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from libmozdata import utils as lmdutils
import os
from . import mail, utils


def clean():
    path = utils.get_config('common', 'log')
    os.remove(path)


def get_msg(path):
    with open(path, 'r') as In:
        data = In.read()
    errors = 0
    for line in data.split('\n'):
        if 'ERROR' in line or 'CRITICAL' in line:
            errors += 1

    if errors == 1:
        return data, []

    return 'There are {} errors: see the log in attachment.'.format(errors), [path]


def send():
    path = utils.get_config('common', 'log')
    try:
        n = os.path.getsize(path)
        if n != 0:
            login_info = utils.get_login_info()
            date = lmdutils.get_date('today')
            msg, files = get_msg(path)
            mail.send(
                login_info['ldap_username'],
                utils.get_config('common', 'on-errors'),
                '[autonag] Something bad happened when running auto-nag the {}'.format(
                    date
                ),
                msg,
                html=False,
                login=login_info,
                dryrun=False,
                files=files,
            )
    except Exception:
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Manage logs')
    parser.add_argument(
        '-c', '--clean', dest='clean', action='store_true', help='Remove the log files'
    )
    parser.add_argument(
        '-s',
        '--send',
        dest='send',
        action='store_true',
        help='Send the log if not empty',
    )
    args = parser.parse_args()
    if args.clean:
        clean()
    if args.send:
        send()
