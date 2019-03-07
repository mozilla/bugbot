# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from . import mail, utils
from .round_robin import RoundRobin


def send_mail(nag, dryrun=False):
    for fb, filenames in nag.items():
        mail.send_from_template(
            'round_robin_fallback_email.html',
            fb,
            'Triage owners need to be updated',
            Cc=utils.get_config('common', 'receivers'),
            dryrun=dryrun,
            filenames=filenames,
            plural=utils.plural,
        )


def check_people(date, dryrun=False):
    rr = RoundRobin()
    # nag is a dict: mozmail -> list of filenames
    nag = rr.get_who_to_nag(date)
    url = 'https://github.com/mozilla/relman-auto-nag/tree/master/auto_nag/scripts/configs/{}'
    nag = {fb: [(fn, url.format(fn)) for fn in fns] for fb, fns in nag.items()}
    send_mail(nag, dryrun=dryrun)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check if next release date is ok')
    parser.add_argument(
        '-d',
        '--dryrun',
        dest='dryrun',
        action='store_true',
        help='Just do the query, and print emails to console without emailing anyone',
    )
    parser.add_argument(
        '-D',
        '--date',
        dest='date',
        action='store',
        default='today',
        help='Date for the query',
    )
    args = parser.parse_args()
    check_people(args.date, dryrun=args.dryrun)
