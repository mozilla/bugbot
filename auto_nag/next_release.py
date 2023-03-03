# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import re

import dateutil.parser
import pytz
import requests
from libmozdata import release_calendar
from libmozdata import release_owners as ro
from libmozdata import utils as lmdutils

from . import logger, mail, utils


def send_mail(next_date, bad_date_nrd, bad_date_ro, dryrun=False):
    mail.send_from_template(
        "next_release_email",
        utils.get_receivers("next-release"),
        "Next release date is not up-to-date",
        dryrun=dryrun,
        next_date=next_date,
        bad_date_nrd=bad_date_nrd,
        bad_date_ro=bad_date_ro,
    )


def check_dates(dryrun=False):
    next_date = utils.get_next_release_date()
    bad_date_nrd = bad_date_ro = None

    pat = re.compile(r"<p>(.*)</p>", re.DOTALL)
    url = "https://wiki.mozilla.org/Template:NextReleaseDate"
    template_page = str(requests.get(url).text)
    m = pat.search(template_page)
    date = dateutil.parser.parse(m.group(1).strip())
    date = pytz.utc.localize(date)

    if date != next_date:
        # so two possibilities:
        #  - Release services people just changed the release date
        #  - something is wrong and we must nag
        now = lmdutils.get_date_ymd("today")
        cal = release_calendar.get_calendar()
        must_nag = True
        for i, c in enumerate(cal):
            if (
                now < c["release date"]
                and i + 1 < len(cal)
                and cal[i + 1]["release date"] == date
            ):
                # The date is just the one after the "normal" release date
                # so here probably someone just changed the date because
                # we're close the merge day
                must_nag = False
                break
        if must_nag:
            bad_date_nrd = date.strftime("%Y-%m-%d")

    owners = ro.get_owners()
    now = lmdutils.get_date_ymd("today")
    for o in owners[::-1]:
        date = o["release date"]
        if now < date:
            if date != next_date:
                bad_date_ro = date.strftime("%Y-%m-%d")
            break

    if bad_date_nrd or bad_date_ro:
        next_date = next_date.strftime("%Y-%m-%d")
        send_mail(next_date, bad_date_nrd, bad_date_ro, dryrun=dryrun)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check if next release date is ok")
    parser.add_argument(
        "--production",
        dest="dryrun",
        action="store_false",
        help="If the flag is not passed, just do the query, and print emails to console without emailing anyone",
    )
    args = parser.parse_args()
    try:
        check_dates(dryrun=args.dryrun)
    except Exception:
        logger.exception("Tool next_release")
