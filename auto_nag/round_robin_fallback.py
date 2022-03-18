# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse

from . import logger, mail, utils
from .round_robin import RoundRobin


def send_mail(nag, dryrun=False):
    for fb, calendars in nag.items():
        mail.send_from_template(
            "round_robin_fallback_email.html",
            fb,
            "Triage owners need to be updated",
            Cc=utils.get_config("common", "receivers"),
            dryrun=dryrun,
            calendars=calendars,
            plural=utils.plural,
        )


def check_people(date, dryrun=False):
    rr = RoundRobin.get_instance()
    # nag is a dict: persons -> list of persons
    #                team -> team name
    nag = rr.get_who_to_nag(date)
    send_mail(nag, dryrun=dryrun)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check if next release date is ok")
    parser.add_argument(
        "-p",
        "--production",
        dest="dryrun",
        action="store_false",
        help="If the flag is not passed, just do the query, and print emails to console without emailing anyone",
    )
    parser.add_argument(
        "-D",
        "--date",
        dest="date",
        action="store",
        default="today",
        help="Date for the query",
    )
    args = parser.parse_args()
    try:
        check_people(args.date, dryrun=args.dryrun)
    except Exception:
        logger.exception("Tool round_robin_fallback")
