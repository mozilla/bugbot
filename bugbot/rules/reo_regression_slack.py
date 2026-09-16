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
bugs are counted in the totals and included in the links like any other, but
never named: no message prints a bug summary, which is the same line
`BzCleaner.get_summary` draws. The top-level bullet says how many of its count
are restricted, because a reader without access opens the link and finds a
shorter list than the number they clicked on. See `restricted_note`.

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

# Shared with the rest of bugbot rather than redeclared as ("S1", "S2") the way the
# REO queries have it. It also carries the pre-S1 names — critical maps to S1, major
# and blocker to S2 (see `constants.OLD_SEVERITY_MAP`) — so an old bug that never had
# its severity restated still lands in the S2+ counts instead of quietly missing from
# them. That is a wider net than bugdash casts, so these numbers can run slightly
# ahead of the REO tab's.
from bugbot.constants import HIGH_SEVERITY

# The channel this rule posts to. Here rather than in `configs/rules.json`
# because it is not a secret, and because changing where an unattended recurring
# message lands should take a code review -- the same reasoning `frontend_triage`
# gives for keeping its component list in code. The bot token is the part that is
# a secret, and that stays in `configs/config.json`.
#
# TEMPORARY: this is currently #tmp-dm-test, a scratch channel for shaking the
# port out. It has to be pointed at the real REO channel before this message is
# meant for anyone to read.
CHANNEL = "C0BLP0WUBED"

BZ_BUGLIST_URL = "https://bugzilla.mozilla.org/buglist.cgi"

RELEASE_PAGE_URL = "https://whattrainisitnow.com/release/?version={}"

WELLNESS_API_URL = "https://whattrainisitnow.com/api/wellness/days/"

# The wellness endpoint answers quickly; the Bugzilla searches get bugbot's own
# `bz_query_timeout`, which is far longer.
HTTP_TIMEOUT_SECONDS = 15

# Every Bugzilla classification except Graveyard, which holds the ~100 retired
# products. Same list bugdash's REO queries use.
#
# "Developer Infrastructure" appearing here and in EXCLUDED_PRODUCTS is not a
# contradiction: the classification also holds Firefox Build System, Conduit and
# Tree Management, which stay in scope, and only the product of the same name is
# dropped.
CLASSIFICATIONS = [
    "Client Software",
    "Components",
    "Developer Infrastructure",
    "Other",
    "Server Software",
]

# The severity that means no triage decision has been made yet. Bugs are filtered
# on this locally, so the value has to be exactly what Bugzilla reports in a bug's
# severity field, which is case sensitive and not always what the same value looks
# like in a search: "N/A" comes back from the API where a query matches it as
# "n/a". Only "--" counts as missing here; N/A is a decision, not the absence of
# one.
MISSING_SEVERITIES = ("--",)

# Products dropped from every query, so their bugs reach no bucket in this
# message.
#
# Not the `exclude_products` key some rules carry in `configs/rules.json`: that one
# subtracts from `BzCleaner`'s default product list, which these classification
# scoped queries never use, so the name would mean something different here.
EXCLUDED_PRODUCTS = ("Testing", "Developer Infrastructure")

# Where the product exclusions are numbered from in a boolean chart. Above every
# slot `regressions_query` uses, including the 11 `with_severities` takes.
EXCLUDED_PRODUCTS_SLOT = 12

# For a component with no team_name, or one missing from the mapping entirely.
# Every component had a team when this was written, so this is only a guard
# against silently dropping bugs out of the per-team line.
UNKNOWN_TEAM = "Unknown team"

# A Slack section block holds at most 3000 characters.
SECTION_LIMIT = 3000

# Above this length a snapshot URL is shortened, and failing that swapped for the
# query URL or dropped entirely -- see `bug_link`. Keeps one very long bug list
# from pushing a section over SECTION_LIMIT.
MAX_SNAPSHOT_URL = 2000

# Slack has no nested lists in message text, so indent sub-bullets by hand.
# Four plain spaces; if Slack ever collapses them, non-breaking spaces (U+00A0)
# are the fix.
SUB_BULLET = "    ◦ "

# What a bug search has to come back with for this message.
#
# `groups` is how a bug is known to be restricted, and the message counts those.
# See `restricted_note`.
#
# No `summary` field. That is the line this message does not cross, and the same
# one `BzCleaner.get_summary` draws.
BUG_FIELDS = "id,severity,product,component,groups"

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


def utc_today() -> datetime.date:
    """Today in UTC: milestone dates are UTC and the cron host may not be."""
    return lmdutils.get_date_ymd("today").date()


def without_excluded_products(slot: int = EXCLUDED_PRODUCTS_SLOT) -> dict:
    """Chart conditions dropping EXCLUDED_PRODUCTS, a numbered slot per product.

    One ANDed notequals per product rather than a single nowords: Bugzilla splits
    a nowords value on whitespace, so "Developer Infrastructure" would be matched
    as the two words separately and drop products nobody asked to exclude.
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

    carry_over adds a condition on the previous version, splitting that set in
    two. False keeps the bugs where status-firefox{version - 1} is one of
    unaffected, ? or ---, so they regressed during this cycle; True negates it,
    leaving the ones that were already there. The two therefore partition every
    open regression affecting the version, and the default of None asks for that
    whole set instead of one side of it.

    Nothing here filters on `bug_group`: an authenticated search returns every bug
    the key can see, so restricted regressions arrive on their own.

    Field numbering is Bugzilla's boolean charts: f/o/v are the field, operator
    and value for a numbered condition, OP and CP open and close a group, j sets
    how a group joins (OR here, AND otherwise) and n negates. The gaps at f7 and
    f9 are harmless, as Bugzilla ignores unused numbers: f7 comes from bugdash,
    f9 from the product exclusions moving to EXCLUDED_PRODUCTS_SLOT.
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

    # Conditions are matched up by their number, so leaving these out above and
    # adding them here changes nothing but the order they appear in the URL.
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
        # n2 attaches to the OP at f2, so it negates the whole f3-f5 group rather
        # than just the first condition in it.
        query["n2"] = "1"

    return query


def with_severities(query: dict, severities: Collection[str]) -> dict:
    """Narrow a query to some severities, for a link that stays live.

    The counts themselves are filtered locally, so this is only needed to build a
    URL when a bug list is too long to link by id. Slot 11 is free: the regressions
    query leaves it unused, and EXCLUDED_PRODUCTS_SLOT starts above it.

    Sorted so the same set of severities always produces the same URL: the order a
    set iterates in is not stable from one process to the next, and `HIGH_SEVERITY`
    is a set.
    """
    return {
        **query,
        "f11": "bug_severity",
        "o11": "anyexact",
        "v11": ", ".join(sorted(severities)),
    }


def snapshot_url(bugs: list[dict]) -> str:
    """A Bugzilla URL listing exactly these bugs, as bugdash's bug lists do.

    Linking the bug ids rather than the query means the list still matches the
    count in the message when it is read days later. order=bug_list keeps
    Bugzilla showing them in the order given rather than re-sorting.

    Built by hand rather than through `utils.get_bz_search_url` so the separators
    stay as commas: percent-encoded they would triple in length, and the length is
    what `MAX_SNAPSHOT_URL` is measuring.

    Restricted bugs are in here with everything else. A reader without access gets
    a shorter list than the count that linked them here, which is what the
    "(n restricted)" note on the bullet is for.
    """
    ids = ",".join(str(bug["id"]) for bug in bugs)

    return f"{BZ_BUGLIST_URL}?bug_id={ids}&order=bug_list"


def shortened_url(url: str) -> str | None:
    """A short Bugzilla URL for a long one, or None if it couldn't be shortened.

    `utils.shorten_long_bz_url` answers a shortener error by returning the URL
    split across several lines (bugbot#1402). Harmless in an email, useless in a
    Slack link, which would end at the first newline — so a multi-line answer is
    treated as a failure here rather than posted.

    Any other failure is swallowed for the same reason: the count is the message
    and the link is a convenience, so a shortener that is down should cost the link
    and nothing more.
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

    label_template is formatted with the count, e.g. "{} New Regressions".

    A snapshot URL that comes out too long is shortened, which keeps the link
    pointing at exactly the bugs counted. Failing that it falls back to
    fallback_query, which is a live query and so can drift from the count beside
    it, and failing that the count is left unlinked. Team lines pass no fallback,
    as reproducing a team as a query means listing all its components.

    Callers are expected to skip empty lists: an empty bug_id would link to a
    broken list, and a count of zero is left out of the message anyway.
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
    """Map every (product, component) to the team that owns it.

    team_name is a Bugzilla field on components, the same one bugdash's Teams
    filter uses. One request covers every product, around 120KB for 2000-odd
    components, which is why it's cached for the life of the run.
    """
    return fetch_component_teams()


def team_of(bug: dict) -> str:
    """The team owning a bug's component."""
    return component_teams().get(ComponentName.from_bug(bug)) or UNKNOWN_TEAM


def team_breakdown(bugs: list[dict]) -> str:
    """Count the bugs owned by each team, busiest team first.

    Every team is listed rather than just the top few, so that the line works
    as a nudge to each team that owns something.
    """
    by_team: dict[str, list[dict]] = {}
    for bug in bugs:
        by_team.setdefault(team_of(bug), []).append(bug)

    ranked = sorted(by_team.items(), key=lambda item: (-len(item[1]), item[0]))

    return ", ".join(bug_link(team_bugs, f"{{}} {team}") for team, team_bugs in ranked)


def restricted_note(bugs: list[dict]) -> str:
    """Say how many of a bug list are restricted, or nothing when none are.

    A bug is restricted when it is in any group at all, not only a security one:
    the note exists to explain why the linked list looks shorter than the count to
    a reader without access, and that gap opens for an employee-confidential or
    partner group just as it does for `core-security`.

    Deliberately plain text rather than part of the link label, so the blue runs as
    far as the thing being counted and no further, and deliberately only used on the
    top-level bullets: repeated on every severity and team sub-bullet it would say
    little and crowd out the counts that are the point of those lines.
    """
    count = sum(1 for bug in bugs if bug.get("groups"))
    if not count:
        return ""

    return f" ({count} restricted)"


def to_blocks(sections: list[str]) -> list[dict]:
    """Wrap the sections of a message as Block Kit sections.

    Slack silently splits a message whose text runs past about 4000 characters
    into several messages, which is what happened when every count linked to a
    full query URL. Snapshot URLs brought the total well under that, but each
    section block gets its own 3000 character allowance, so keeping the sections
    means a busier cycle can't start splitting the message again.

    A section that does overflow raises rather than posting something malformed.
    The team breakdown is the part that could get there, at roughly 90 characters
    per team; capping or splitting it is the fix if that ever fires.
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
    """The text of any block, for printing a message instead of posting it.

    Section and header blocks keep their text in one place and context blocks in
    a list of elements, so a dry run has to handle both rather than assume the
    shape of the blocks it was handed.
    """
    if "elements" in block:
        return " ".join(element["text"] for element in block["elements"])

    return block["text"]["text"]


def versions_to_report() -> dict[str, int]:
    """The current version of each channel, with what was read written to the log.

    From the trains API rather than through `BzCleaner.init_versions`:
    `utils.get_checked_versions` returns nothing on merge day, and
    `has_enough_data` would then skip the run on exactly the day this message
    has its own wording for.
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
    """Post the state of this cycle's open release regressions to Slack.

    A `BzCleaner` that reports to Slack instead of by email: the searches, the
    arguments, the `must_run` gate and the error handling are all the
    framework's, and `get_email_data` posts the message and returns nothing to
    mail. The days it runs on are `must_run` in `configs/rules.json`.
    """

    # Where the message goes. A `--channel` run overrides it, so this is the
    # channel the cron posts to; see `parse_custom_arguments`.
    channel = CHANNEL

    def description(self) -> str:
        return "REO release regression cycle summary posted to Slack"

    def all_include_fields(self) -> bool:
        # The fields a search asks for are `BUG_FIELDS` and nothing else.
        # `BzCleaner` would otherwise add `summary` to every query, which is the
        # one field this message does not print -- see `restricted_note`.
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
        """Keep every field of the bug, keyed by its id.

        `BzCleaner`'s own handler reduces a bug to the columns of an email
        table, its summary included. This message reports counts and
        breakdowns, so it needs the fields it asked for and none of the rest.
        """
        data[str(bug["id"])] = bug

    def fetch_bugs(self, query: dict, fields: str = BUG_FIELDS) -> list[dict]:
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
        """Post the message to Slack, or print it when the run isn't for real.

        A dry run prints what it would have posted, so `--production` means here
        what it means for every other rule. `test_mode` is honoured alongside it
        for the reason `triage_owner_rotations` honours it: a test run must reach
        nobody.
        """
        if self.dryrun or self.test_mode:
            print("DRY RUN: message not posted.\n")
            for block in blocks:
                print(block_text(block))
            return

        # HEADING is the message's notification fallback text, which is what a
        # client that cannot render blocks shows instead of them.
        slack.post_to_slack(self.channel, HEADING, blocks=blocks)
        logger.info("Rule %s posted to %s", self.name(), self.channel)

    def get_email_data(self, date: str) -> EmailData:
        """Post the message, and give `send_email` nothing to send.

        The report is the Slack message rather than an email, and an empty list
        is what stops one being sent -- the same way `security_affected_versions`
        runs the pipeline for the needinfos it posts and mails no summary. The
        "No data" line `send_email` then logs is about that email, not about the
        message, which has been posted by the time it is written.
        """
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
