# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Post the REO release regression cycle summary to Slack.

For Release, Beta and Nightly it reports two bug lists that together partition
every open regression affecting the version: "new regressions", affected in N
while N-1 is unaffected or unknown, and "carry over regressions", the same query
negated. Each count is broken down by severity, New Regressions also by owning
team, and Beta and Nightly get a working day countdown to the end of the cycle.

The regressions that need chasing rather than counting are the other rule,
`reo_regression_slack_daily`.
"""

import argparse
import datetime
import functools
import re
from collections.abc import Collection
from typing import Any

import requests
from libmozdata import utils as lmdutils
from libmozdata.fx_trains import FirefoxTrains

from bugbot import logger, slack, utils
from bugbot.bzcleaner import Bug, BzCleaner, BzParams, EmailData
from bugbot.components import ComponentName, fetch_component_teams

# Also matches the pre-S1 severity names, so these counts can run slightly ahead
# of the REO tab's.
from bugbot.constants import HIGH_SEVERITY

# TEMPORARY: #tmp-dm-test, a scratch channel for shaking the port out. It has to
# be pointed at the real REO channel before this message is meant to be read.
CHANNEL = "C0BLP0WUBED"

BZ_BUGLIST_URL = "https://bugzilla.mozilla.org/buglist.cgi"

RELEASE_PAGE_URL = "https://whattrainisitnow.com/release/?version={}"

WELLNESS_API_URL = "https://whattrainisitnow.com/api/wellness/days/"

HTTP_TIMEOUT_SECONDS = 15

# Every classification except Graveyard, as bugdash's REO queries have it.
CLASSIFICATIONS = [
    "Client Software",
    "Components",
    "Developer Infrastructure",
    "Other",
    "Server Software",
]

# Bugzilla reports a bug with no triage decision as "--". N/A is a decision, and
# comes back from the API capitalised even though a query matches it as "n/a".
MISSING_SEVERITIES = ("--",)

# Dropped from every query. The Developer Infrastructure classification stays in
# scope; only the product of the same name goes.
EXCLUDED_PRODUCTS = ("Testing", "Developer Infrastructure")

# Above every slot the query uses, including the 11 `with_severities` takes.
EXCLUDED_PRODUCTS_SLOT = 12

UNKNOWN_TEAM = "Unknown team"

# A Slack section block holds at most 3000 characters.
SECTION_LIMIT = 3000

# Above this length a snapshot URL is shortened; see `bug_link`.
MAX_SNAPSHOT_URL = 2000

# Slack has no nested lists in message text, so indent sub-bullets by hand.
SUB_BULLET = "    ◦ "

# `groups` is how a bug is known to be restricted. No `summary`: the message
# names no bug, so restricted ones are counted and linked but never named.
BUG_FIELDS = "id,severity,product,component,groups"

# Stands in for a milestone key, as the last beta is numbered differently from
# one version to the next (beta_10 for 154, beta_5 under the 2 week cadence).
LAST_BETA = "last_beta"

# The milestone ending each channel's cycle, and the cycle's name. Release has no
# equivalent deadline, so it gets no countdown.
CYCLE_ENDS = {
    "beta": ("Beta", LAST_BETA),
    "nightly": ("Nightly", "merge_day"),
}

# Custom emoji in the Mozilla workspace. A name that doesn't exist there renders
# as the literal :name: rather than failing.
CHANNEL_EMOJI = {
    "release": ":firefox-browser:",
    "beta": ":beta-browser:",
    "nightly": ":nightly-browser:",
}

HEADING = "REO release regression status:"

# So a silent channel reads as good news rather than as the script having failed.
NOTHING_TO_REPORT = "•  No open release regressions"


def utc_today() -> datetime.date:
    """Today in UTC: milestone dates are UTC and the cron host may not be."""
    return lmdutils.get_date_ymd("today").date()


def without_excluded_products(slot: int = EXCLUDED_PRODUCTS_SLOT) -> dict:
    """Chart conditions dropping EXCLUDED_PRODUCTS, a numbered slot per product.

    One notequals per product rather than a nowords, which Bugzilla would split on
    whitespace and match "Developer Infrastructure" as two words.
    """
    conditions: dict = {}
    for offset, product in enumerate(EXCLUDED_PRODUCTS):
        number = slot + offset
        conditions |= {
            f"f{number}": "product",
            f"o{number}": "notequals",
            f"v{number}": product,
        }

    return conditions


def regressions_query(version: int, carry_over: bool | None = None) -> dict:
    """Build the open regressions query for a version.

    Bugs with all of the following:
    - regression keyword
    - open (unresolved)
    - status-firefox{version} is affected
    Bugs with any of the following are ignored:
    - tracking-firefox{version} is -
    - stalled or intermittent-failure keywords
    - within one of EXCLUDED_PRODUCTS

    carry_over splits that set in two: False keeps the bugs where
    status-firefox{version - 1} is unaffected, ? or ---, so they regressed during
    this cycle, and True negates it. None asks for the whole set.

    The gaps in the chart numbering come from bugdash and are harmless, as
    Bugzilla ignores unused numbers.
    """
    query = {
        "classification": CLASSIFICATIONS,
        "keywords": "regression",
        "keywords_type": "allwords",
        "resolution": "---",
        "f1": utils.get_flag(version, "status", "release"),
        "o1": "equals",
        "v1": "affected",
        "f8": utils.get_flag(version, "tracking", "release"),
        "o8": "notequals",
        "v8": "-",
        "f10": "keywords",
        "o10": "nowordssubstr",
        "v10": "stalled,intermittent-failure",
        **without_excluded_products(),
    }

    if carry_over is None:
        return query

    previous = utils.get_flag(version - 1, "status", "release")
    query |= {
        "f2": "OP",
        "j2": "OR",
        "f3": previous,
        "o3": "equals",
        "v3": "unaffected",
        "f4": previous,
        "o4": "equals",
        "v4": "?",
        "f5": previous,
        "o5": "equals",
        "v5": "---",
        "f6": "CP",
    }

    if carry_over:
        # n2 attaches to the OP at f2, so it negates the whole f3-f5 group.
        query["n2"] = "1"

    return query


def with_severities(query: dict, severities: Collection[str]) -> dict:
    """Narrow a query to some severities, for a link that stays live.

    Sorted so the same severities always produce the same URL, as `HIGH_SEVERITY`
    is a set.
    """
    return {
        **query,
        "f11": "bug_severity",
        "o11": "anyexact",
        "v11": ", ".join(sorted(severities)),
    }


def snapshot_url(bugs: list[dict]) -> str:
    """A Bugzilla URL listing exactly these bugs, so it still matches the count.

    Built by hand rather than through `utils.get_bz_search_url` so the separators
    stay as commas: percent-encoded they would triple the length
    `MAX_SNAPSHOT_URL` measures.
    """
    ids = ",".join(str(bug["id"]) for bug in bugs)

    return f"{BZ_BUGLIST_URL}?bug_id={ids}&order=bug_list"


def shortened_url(url: str) -> str | None:
    """A short Bugzilla URL for a long one, or None if it couldn't be shortened.

    `utils.shorten_long_bz_url` answers an error with the URL split across lines
    (bugbot#1402), which a Slack link would end at the first newline, so that
    counts as a failure too.
    """
    try:
        short = utils.shorten_long_bz_url(url)
    except Exception:
        logger.exception("Could not shorten a Bugzilla URL")
        return None

    if "\n" in short or len(short) > MAX_SNAPSHOT_URL:
        return None

    return short


def bug_link(
    bugs: list[dict], label_template: str, fallback_query: dict | None = None
) -> str:
    """Format a non-empty bug list as a Slack link labelled with its count.

    An over-long snapshot URL is shortened, then falls back to fallback_query,
    which is live and so can drift from the count, then to no link at all. Team
    lines pass no fallback, as reproducing a team as a query means listing all its
    components.
    """
    label = label_template.format(len(bugs))
    snapshot = snapshot_url(bugs)

    if len(snapshot) <= MAX_SNAPSHOT_URL:
        return f"<{snapshot}|{label}>"

    url = shortened_url(snapshot)
    if url is None and fallback_query is not None:
        url = utils.get_bz_search_url(fallback_query)

    if url is None:
        return label

    return f"<{url}|{label}>"


@functools.cache
def component_teams() -> dict[ComponentName, str]:
    """Map every (product, component) to the team that owns it, in one request."""
    return fetch_component_teams()


def team_of(bug: dict) -> str:
    """The team owning a bug's component."""
    return component_teams().get(ComponentName.from_bug(bug)) or UNKNOWN_TEAM


def team_breakdown(bugs: list[dict]) -> str:
    """Count the bugs owned by each team, busiest team first."""
    by_team: dict[str, list[dict]] = {}
    for bug in bugs:
        by_team.setdefault(team_of(bug), []).append(bug)

    ranked = sorted(by_team.items(), key=lambda item: (-len(item[1]), item[0]))

    return ", ".join(bug_link(team_bugs, f"{{}} {team}") for team, team_bugs in ranked)


def restricted_note(bugs: list[dict]) -> str:
    """Say how many of a bug list are restricted, or nothing when none are.

    Any group counts, not only a security one: this explains why the linked list
    looks shorter than the count to a reader without access.
    """
    count = sum(1 for bug in bugs if bug.get("groups"))
    if not count:
        return ""

    return f" ({count} restricted)"


def to_blocks(sections: list[str]) -> list[dict]:
    """Wrap the sections of a message as Block Kit sections.

    Slack silently splits a message past about 4000 characters, where each section
    block gets its own allowance. An overflowing section raises rather than
    posting something malformed.
    """
    for section in sections:
        if len(section) > SECTION_LIMIT:
            raise RuntimeError(
                f"Slack section block is {len(section)} characters, over the "
                f"{SECTION_LIMIT} limit:\n{section[:200]}..."
            )

    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": section}}
        for section in sections
    ]


def block_text(block: dict) -> str:
    """The text of any block, for printing a message instead of posting it."""
    if "elements" in block:
        return " ".join(element["text"] for element in block["elements"])

    return block["text"]["text"]


def versions_to_report() -> dict[str, int]:
    """The current version of each channel, logging what was read.

    Not through `BzCleaner.init_versions`: `utils.get_checked_versions` returns
    nothing on merge day, which is a day this message has wording for.
    """
    versions = utils.get_versions_from_trains()
    logger.info(
        "Reporting Firefox %s release / %s beta / %s nightly",
        versions["release"],
        versions["beta"],
        versions["nightly"],
    )

    return versions


@functools.cache
def wellness_days() -> frozenset[datetime.date]:
    """Fetch the days off that don't count as working days.

    libmozdata's `FirefoxTrains` doesn't cover this endpoint.
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

    Mirrors ReleaseInsights\\Duration::workDays(), so this agrees with the
    countdowns on the release pages.
    """
    today = utc_today()
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

    Sorting on the number matters: as strings, beta_9 would come after beta_10.
    """
    if milestone == LAST_BETA:
        betas = [key for key in schedule if re.fullmatch(r"beta_\d+", key)]
        milestone = max(betas, key=lambda key: int(key.removeprefix("beta_")))

    return lmdutils.get_date_ymd(schedule[milestone]).date()


def cycle_countdown(version: int, channel: str) -> str:
    """A countdown to the end of this version's time on the channel.

    The deadline and the days after it read badly as a countdown ("in 0 working
    days"), so they get their own wording.
    """
    if channel not in CYCLE_ENDS:
        return ""

    cycle, milestone = CYCLE_ENDS[channel]
    label = f"End of {cycle}"
    end = milestone_date(release_schedule(version), milestone)
    today = utc_today()

    if end < today:
        return f"{cycle} cycle finished"

    if end == today:
        return f"{label} today"

    if end == today + datetime.timedelta(days=1):
        return f"{label} {end:%Y-%m-%d} — tomorrow"

    days = work_days_until(end)
    return f'{label} {end:%Y-%m-%d} in {days} {utils.plural("working day", days)}'


class ReoRegressionSlack(BzCleaner):
    """A `BzCleaner` that reports to Slack instead of by email.

    The days it runs on are `must_run` in `configs/rules.json`.
    """

    # Overridden by a `--channel` run, so this is the channel the cron posts to.
    channel = CHANNEL

    def description(self) -> str:
        return "REO release regression cycle summary posted to Slack"

    def all_include_fields(self) -> bool:
        # `BzCleaner` would otherwise add `summary` to every query.
        return True

    def has_default_products(self) -> bool:
        # Scoped by classification instead, as bugdash's REO queries are.
        return False

    def filter_no_nag_keyword(self) -> bool:
        # A [no-nag] bug is still one the cycle is carrying, and dropping those
        # would put the counts out of step with the REO tab.
        return False

    def add_custom_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--channel",
            action="store",
            default="",
            help=(
                f"Slack channel ID to post to, overriding {CHANNEL}. Useful to "
                "shake the message out somewhere else without editing the code."
            ),
        )

    def parse_custom_arguments(self, args: argparse.Namespace) -> None:
        self.channel = args.channel or CHANNEL

    def get_bz_params(self, date: str) -> BzParams:
        """The query the running `get_bugs()` call is for. See `fetch_bugs`."""
        return self.params

    def bughandler(self, bug: Bug, data: dict[str, Any]) -> None:
        """Keep every field, where `BzCleaner` would keep the email columns."""
        data[str(bug["id"])] = bug

    def fetch_bugs(self, query: dict, fields: str = BUG_FIELDS) -> list[dict]:
        """Run one of this rule's queries through `BzCleaner`'s search path.

        Two queries per channel, each set here and read back by `get_bz_params`,
        the way `warn_regressed_by` steps through its two. libmozdata only pages a
        query carrying none of count_only, limit, order or offset, so no query
        here may add one.
        """
        self.params = {**query, "include_fields": fields}

        return list(self.get_bugs().values())

    def regression_group(
        self, version: int, carry_over: bool, label: str, by_team: bool = False
    ) -> str:
        """Build the bullet and severity sub-bullets for one bug list.

        Split locally rather than queried per subset, so the sub-bullets are
        guaranteed to be part of the count above them. Empty lists are left out of
        the message entirely.
        """
        query = regressions_query(version, carry_over)
        bugs = self.fetch_bugs(query)
        if not bugs:
            return ""

        link = bug_link(bugs, f"{{}} {label} Regressions", query)
        lines = [f"• {link}{restricted_note(bugs)}"]

        if by_team:
            lines.append(SUB_BULLET + team_breakdown(bugs))

        severity_counts = []
        for severities, template in (
            (HIGH_SEVERITY, "{} S2+"),
            (MISSING_SEVERITIES, "{} missing severity"),
        ):
            subset = [bug for bug in bugs if bug["severity"] in severities]
            if subset:
                severity_counts.append(
                    bug_link(subset, template, with_severities(query, severities))
                )

        if severity_counts:
            lines.append(SUB_BULLET + ", ".join(severity_counts))

        return "\n".join(lines)

    def post_message(self, blocks: list[dict]) -> None:
        """Post the message to Slack, or print it on a dry or test run."""
        if self.dryrun or self.test_mode:
            print("DRY RUN: message not posted.\n")
            for block in blocks:
                print(block_text(block))
            return

        # HEADING is the notification fallback text, which is what a client that
        # cannot render blocks shows instead of them.
        slack.post_to_slack(self.channel, HEADING, blocks=blocks)
        logger.info("Rule %s posted to %s", self.name(), self.channel)

    def get_email_data(self, date: str) -> EmailData:
        """Post the message, and return no data so `send_email` sends nothing."""
        self.post_message(self.blocks(versions_to_report()))

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

        return to_blocks(sections)


if __name__ == "__main__":
    ReoRegressionSlack().run()
