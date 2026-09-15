# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Post the REO release regression cycle summary to Slack.

For Release, Beta and Nightly it reports two bug lists, built from the bug set
behind the REO tab of https://bugdash.moz.tools/:

- "new regressions" carry the regression keyword and are affected in version N
  while N-1 is unaffected or unknown, so they regressed during this cycle
- "carry over regressions" are the same query negated: N-1 has a real status, so
  the bug was already there

Those two partition every open regression affecting N. Each count is broken down
by severity, with New Regressions also broken down by owning team. Beta and
Nightly get a working day countdown to the end of their cycle.

Every count links to a Bugzilla list of exactly the bugs counted. Restricted
bugs are counted and linked like any other but never named; see
`bugbot.reo_regressions`, which also holds the queries and the posting.

The regressions that need chasing rather than counting are the other rule,
`reo_regression_slack_daily`.
"""

import argparse
import datetime
import functools
import re
from typing import Any

import requests
from libmozdata import utils as lmdutils
from libmozdata.fx_trains import FirefoxTrains

from bugbot import reo_regressions as reo
from bugbot import utils
from bugbot.bzcleaner import Bug, BzCleaner, BzParams, EmailData

RELEASE_PAGE_URL = "https://whattrainisitnow.com/release/?version={}"

WELLNESS_API_URL = "https://whattrainisitnow.com/api/wellness/days/"

# The wellness endpoint answers quickly; the Bugzilla searches get bugbot's own
# `bz_query_timeout`, which is far longer.
HTTP_TIMEOUT_SECONDS = 15

# Stands in for a milestone key, as the last beta is numbered differently from
# one version to the next (beta_10 for 154, beta_5 under the 2 week cadence).
LAST_BETA = "last_beta"

# The milestone that ends each channel's cycle, and the cycle's name. Both the
# countdown ("End of Beta ...") and the finished line ("Beta cycle finished") are
# built from that one name, so they can't drift apart. Release has no equivalent
# deadline, so it gets no countdown.
CYCLE_ENDS = {
    "beta": ("Beta", LAST_BETA),
    "nightly": ("Nightly", "merge_day"),
}

# Custom emoji in the Mozilla workspace, one per channel. A name that doesn't exist
# there renders as the literal :name: rather than failing, so these have to stay
# in step with the workspace.
CHANNEL_EMOJI = {
    "release": ":firefox-browser:",
    "beta": ":beta-browser:",
    "nightly": ":nightly-browser:",
}

HEADING = "REO release regression status:"

# Shown instead of dropping a channel entirely, so a silent channel reads as
# good news rather than as the script having failed.
NOTHING_TO_REPORT = "•  No open release regressions"


@functools.cache
def wellness_days() -> frozenset[datetime.date]:
    """Fetch the days off that don't count as working days.

    libmozdata's `FirefoxTrains` covers the schedule and owners endpoints but not
    this one, so it is fetched directly. Moving it there is the tidier home if a
    second caller ever turns up.
    """
    response = requests.get(
        WELLNESS_API_URL,
        headers={"User-Agent": "bugbot"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    return frozenset(datetime.date.fromisoformat(day) for day in response.json())


def work_days_until(end: datetime.date) -> int:
    """Count working days between today and end, end excluded.

    Mirrors ReleaseInsights\\Duration::workDays() so this agrees with the
    countdowns on the release pages: weekends, wellness days and the current
    day are all left out.
    """
    today = reo.utc_today()
    days = (end - today).days
    if days <= 0:
        return 0

    # Counting from tomorrow is what leaves the current day out.
    return sum(
        1
        for offset in range(1, days)
        if (day := today + datetime.timedelta(days=offset)).weekday() < 5  # Mon-Fri
        and day not in wellness_days()
    )


def release_schedule(version: int) -> dict:
    """A version's milestone dates from the trains API, cached by libmozdata."""
    return FirefoxTrains.get_instance().get_release_schedule(str(version))


def milestone_date(schedule: dict, milestone: str) -> datetime.date:
    """The date of a milestone, resolving LAST_BETA to the highest numbered beta.

    The number of betas differs per version, so the last one has to be found
    rather than named. Sorting on the number matters: as strings, beta_9 would
    come after beta_10.
    """
    if milestone == LAST_BETA:
        betas = [key for key in schedule if re.fullmatch(r"beta_\d+", key)]
        milestone = max(betas, key=lambda key: int(key.removeprefix("beta_")))

    return lmdutils.get_date_ymd(schedule[milestone]).date()


def cycle_countdown(version: int, channel: str) -> str:
    """A countdown to the end of this version's time on the channel.

    Beta ends with the last beta build; Nightly ends on merge day, when the
    version moves to Beta. Release has no such deadline.

    The version numbers roll over on merge day, so the day of and the days after
    that deadline each only show up briefly, but they read badly as a countdown
    ("in 0 working days") and so get their own wording.
    """
    if channel not in CYCLE_ENDS:
        return ""

    cycle, milestone = CYCLE_ENDS[channel]
    label = f"End of {cycle}"
    end = milestone_date(release_schedule(version), milestone)
    today = reo.utc_today()

    if end < today:
        return f"{cycle} cycle finished"

    if end == today:
        return f"{label} today"

    if end == today + datetime.timedelta(days=1):
        return f"{label} {end:%Y-%m-%d} — tomorrow"

    days = work_days_until(end)
    return f'{label} {end:%Y-%m-%d} in {days} {utils.plural("working day", days)}'


class ReoRegressionSlack(BzCleaner):
    """Post the state of this cycle's open release regressions to Slack.

    A `BzCleaner` that reports to Slack instead of by email: the searches, the
    arguments, the `must_run` gate and the error handling are all the
    framework's, and `get_email_data` posts the message and returns nothing to
    mail. The days it runs on are `must_run` in `configs/rules.json`.
    """

    # Where the message goes. A `--channel` run overrides it, so this is the
    # channel the cron posts to; see `parse_custom_arguments`.
    channel = reo.CHANNEL

    def description(self) -> str:
        return "REO release regression cycle summary posted to Slack"

    def all_include_fields(self) -> bool:
        # The fields a search asks for are `reo.BUG_FIELDS` and nothing else.
        # `BzCleaner` would otherwise add `summary` to every query, which is the
        # one field no message here prints -- see `reo.restricted_note`.
        return True

    def has_default_products(self) -> bool:
        # The query is scoped by classification, as bugdash's REO queries are;
        # the default product list would report a different bug set.
        return False

    def filter_no_nag_keyword(self) -> bool:
        # This message counts bugs rather than nagging about them, and a
        # [no-nag] bug is still one the cycle is carrying. Dropping those would
        # put the counts out of step with the REO tab.
        return False

    def add_custom_arguments(self, parser: argparse.ArgumentParser) -> None:
        reo.add_channel_argument(parser)

    def parse_custom_arguments(self, args: argparse.Namespace) -> None:
        self.channel = args.channel or reo.CHANNEL

    def get_bz_params(self, date: str) -> BzParams:
        """The query the running `get_bugs()` call is for. See `fetch_bugs`."""
        return self.params

    def bughandler(self, bug: Bug, data: dict[str, Any]) -> None:
        """Keep every field of the bug, keyed by its id.

        `BzCleaner`'s own handler reduces a bug to the columns of an email
        table, its summary included. This message reports counts and
        breakdowns, so it needs the fields it asked for and none of the rest.
        """
        data[str(bug["id"])] = bug

    def fetch_bugs(self, query: dict, fields: str = reo.BUG_FIELDS) -> list[dict]:
        """Run one of this rule's queries through `BzCleaner`'s search path.

        Several queries per run -- two per channel -- each one set here and read
        back by `get_bz_params`, the way `warn_regressed_by` steps through its
        two. Going through `get_bugs` is what attaches bugbot's API key, which
        is the whole reason this sees restricted bugs, along with the query
        timeout and the paging. libmozdata pages a search itself -- counting
        first, then walking the results in chunks -- but only for a query
        carrying none of count_only, limit, order or offset, so no query here
        may add one.

        Fetching the bugs rather than asking for count_only is what lets the
        severity and team breakdowns be derived from one request, and lets each
        count link to the exact bugs behind it.
        """
        self.params = {**query, "include_fields": fields}

        return list(self.get_bugs().values())

    def regression_group(
        self, version: int, carry_over: bool, label: str, by_team: bool = False
    ) -> str:
        """Build the bullet and severity sub-bullets for one bug list.

        The list is fetched once and split by severity and team here, rather than
        asking Bugzilla for each subset, so the sub-bullets are guaranteed to be
        part of the count above them.

        Bug lists that are empty are left out entirely rather than reported as a
        zero, so a quiet channel is short instead of a wall of "0". Returns an
        empty string when there are no bugs at all.
        """
        query = reo.regressions_query(version, carry_over)
        bugs = self.fetch_bugs(query)
        if not bugs:
            return ""

        link = reo.bug_link(bugs, f"{{}} {label} Regressions", query)
        lines = [f"• {link}{reo.restricted_note(bugs)}"]

        if by_team:
            lines.append(reo.SUB_BULLET + reo.team_breakdown(bugs))

        severity_counts = []
        for severities, template in (
            (reo.HIGH_SEVERITY, "{} S2+"),
            (reo.MISSING_SEVERITIES, "{} missing severity"),
        ):
            subset = [bug for bug in bugs if bug["severity"] in severities]
            if subset:
                severity_counts.append(
                    reo.bug_link(
                        subset, template, reo.with_severities(query, severities)
                    )
                )

        if severity_counts:
            lines.append(reo.SUB_BULLET + ", ".join(severity_counts))

        return "\n".join(lines)

    def get_email_data(self, date: str) -> EmailData:
        """Post the message, and give `send_email` nothing to send.

        The report is the Slack message rather than an email, and an empty list
        is what stops one being sent -- the same way `security_affected_versions`
        runs the pipeline for the needinfos it posts and mails no summary. The
        "No data" line `send_email` then logs is about that email, not about the
        message, which has been posted by the time it is written.
        """
        reo.post_message(
            self, self.channel, HEADING, self.blocks(reo.versions_to_report())
        )

        return []

    def blocks(self, versions: dict[str, int]) -> list[dict]:
        """Build the cycle summary as Block Kit sections, one per bug list."""
        sections = [HEADING]

        for channel in ("release", "beta", "nightly"):
            version = versions[channel]
            page = RELEASE_PAGE_URL.format(version)
            emoji = CHANNEL_EMOJI[channel]
            header = f"{emoji} *<{page}|Fx{version} {channel.title()}>*"

            countdown = cycle_countdown(version, channel)
            if countdown:
                header += f"\n{countdown}"

            groups = [
                group
                for group in (
                    self.regression_group(version, False, "New", by_team=True),
                    self.regression_group(version, True, "Carry Over"),
                )
                if group
            ]

            if not groups:
                sections.append(f"{header}\n{NOTHING_TO_REPORT}")
                continue

            # The header rides along with the first surviving group, so that a
            # channel with only carry over bugs isn't left with a stray heading.
            sections.append(f"{header}\n{groups[0]}")
            sections.extend(groups[1:])

        return reo.to_blocks(sections)


if __name__ == "__main__":
    ReoRegressionSlack().run()
