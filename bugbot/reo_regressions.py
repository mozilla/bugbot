# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Shared parts of the rules that post the REO release regressions to Slack.

Two rules are built on this, both over the bug set behind the REO tab of
https://bugdash.moz.tools/:

- `bugbot.rules.reo_regression_slack`, the cycle summary, Mon and Thu
- `bugbot.rules.reo_regression_slack_daily`, the action required message, every
  weekday

Both are `BzCleaner` rules, so the searches go out through `get_bz_params` and
`get_bugs`, and the run itself -- the rule's name, its arguments, its `must_run`
gate, its logging and its error handling -- is the framework's. What lives here
is what the two of them share on top of that: the open regressions query, the
Bugzilla link building, the team breakdown, the Block Kit wrapping and the
posting. What is one message's own -- its heading, its cadence, its buckets --
lives in that rule.

A few things here have one caller today, and each says so where it is defined.
They are kept here because of what they are rather than who uses them: a
condition on a query this module builds, or a fact about Slack's markup. Moving
each one to whichever rule happens to call it would leave the next reader
looking in two files for one vocabulary, and moving it back is what adding the
second caller would mean.

Shaped after `bugbot.multinaggers` and `bugbot.topcrash`: a module here holding
what rules under `bugbot/rules` share.

Restricted bugs are counted in the totals and included in the links like any
other, but never named: no message prints a bug summary, which is the same line
`BzCleaner.get_summary` draws. The top-level bullet says how many of its count
are restricted, because a reader without access opens the link and finds a
shorter list than the number they clicked on, and the note is what explains the
gap. See `restricted_note`.
"""

import argparse
import datetime
import functools
from collections.abc import Collection

from bugbot import logger, slack, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.components import ComponentName, fetch_component_teams

# Shared with the rest of bugbot rather than redeclared as ("S1", "S2") the way the
# REO queries have it. It also carries the pre-S1 names — critical maps to S1, major
# and blocker to S2 (see `constants.OLD_SEVERITY_MAP`) — so an old bug that never had
# its severity restated still lands in the S2+ counts instead of quietly missing from
# them. That is a wider net than bugdash casts, so these numbers can run slightly
# ahead of the REO tab's.
#
# Re-exported here rather than imported by each rule, so that reasoning is written
# down once for both messages.
from bugbot.constants import HIGH_SEVERITY  # noqa: F401

# The channel both rules post to. Here rather than in `configs/rules.json`
# because it is not a secret, and because changing where an unattended recurring
# message lands should take a code review -- the same reasoning `frontend_triage`
# gives for keeping its component list in code. The bot token is the part that is
# a secret, and that stays in `configs/config.json`.
#
# TEMPORARY: this is currently #tmp-dm-test, a scratch channel for shaking the
# port out. It has to be pointed at the real REO channel before either message is
# meant for anyone to read.
CHANNEL = "C0BLP0WUBED"

BZ_BUGLIST_URL = "https://bugzilla.mozilla.org/buglist.cgi"

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

# Products dropped from every query, so their bugs reach neither message and no
# bucket in them. Excluded at the query rather than per bucket, so a product here
# is out of the cycle summary, all the daily buckets and the burndown lines alike.
#
# Not the `exclude_products` key some rules carry in `configs/rules.json`: that one
# subtracts from `BzCleaner`'s default product list, which these classification
# scoped queries never use, so the name would mean something different here.
EXCLUDED_PRODUCTS = ("Testing", "Developer Infrastructure")

# Where the product exclusions are numbered from in a boolean chart. Above every
# slot either query uses -- `regressions_query` here and `burndown_query` in the
# daily rule -- including the 11 `with_severities` takes.
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

# Slack renders this back as >. Sending the character itself would work where it
# is used now, but it ends a link's label at the first > and opens a blockquote at
# the start of a line, so a label or bullet reworded around it would break in ways
# that are easy to miss. The entity is never wrong.
#
# The daily rule's "> 24 hours" is the only use today. It is here rather than
# there because it is a fact about Slack's markup, like SUB_BULLET below, and not
# about that message.
GREATER_THAN = "&gt;"

# Slack has no nested lists in message text, so indent sub-bullets by hand.
# Four plain spaces; if Slack ever collapses them, non-breaking spaces (U+00A0)
# are the fix.
SUB_BULLET = "    ◦ "

# What a bug search has to come back with for either message. The cycle summary
# needs no more than this and takes it as `fetch_bugs`'s default; the daily rule
# extends it, as it ages every bug and the timestamps it ages from live on the
# bug itself.
#
# `groups` is in here rather than in one of those extensions: it is how a bug is
# known to be restricted, and every message counts those. See `restricted_note`.
#
# No `summary` field, here or in either extension. That is the line neither
# message crosses, and the same one `BzCleaner.get_summary` draws.
BUG_FIELDS = "id,severity,product,component,groups"


def utc_today() -> datetime.date:
    """Today in UTC: milestone dates are UTC and the cron host may not be."""
    return datetime.datetime.now(datetime.timezone.utc).date()


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


def status_flag(version: int) -> str:
    """The status flag for a Firefox version, e.g. `cf_status_firefox150`.

    Built by `utils.get_flag` rather than concatenated: that is the one place
    version numbers become flag names anywhere in bugbot. Its channel argument only
    changes the name for ESR, and every version these queries run over is a desktop
    one, so which channel the version happens to be on doesn't enter into it.
    """
    return utils.get_flag(version, "status", "release")


def tracking_flag(version: int) -> str:
    """The tracking flag for a Firefox version, e.g. `cf_tracking_firefox150`.

    See `status_flag` for why this goes through `utils.get_flag`.
    """
    return utils.get_flag(version, "tracking", "release")


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
        "f1": status_flag(version),
        "o1": "equals",
        "v1": "affected",
        "f8": tracking_flag(version),
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
    previous = status_flag(version - 1)
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

    The cycle summary is the only caller today. It is here rather than there
    because it edits `regressions_query`'s chart, and which slot it may take can
    only be answered next to the slots that query and the daily rule's burndown
    query have already spoken for.

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


def query_url(query: dict) -> str:
    """A Bugzilla URL that re-runs a query, so its results change over time."""
    return utils.get_bz_search_url(query)


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
    as reproducing a team as a query means listing all its components, so before
    the shortener they lost their link entirely.

    Callers are expected to skip empty lists: an empty bug_id would link to a
    broken list, and a count of zero is left out of the message anyway.
    """
    label = label_template.format(len(bugs))
    snapshot = snapshot_url(bugs)

    if len(snapshot) <= MAX_SNAPSHOT_URL:
        return f"<{snapshot}|{label}>"

    url = shortened_url(snapshot)
    if url is None and fallback_query is not None:
        url = query_url(fallback_query)

    if url is None:
        return label

    return f"<{url}|{label}>"


def restricted_note(bugs: list[dict]) -> str:
    """Say how many of a bug list are restricted, or nothing when none are.

    A bug is restricted when it is in any group at all, not only a security one:
    the note exists to explain why the linked list looks shorter than the count to
    a reader without access, and that gap opens for an employee-confidential or
    partner group just as it does for `core-security`. That is a wider test than
    the `bug_group ~ "sec"` branch in the daily rule's burndown query, which is
    asking a different question — whether a fix is worth chasing, not whether it is
    readable.

    Deliberately plain text rather than part of the link label, so the blue runs as
    far as the thing being counted and no further, and deliberately only used on the
    top-level bullets: repeated on every severity and team sub-bullet it would say
    little and crowd out the counts that are the point of those lines.
    """
    count = sum(1 for bug in bugs if bug.get("groups"))
    if not count:
        return ""

    return f" ({count} restricted)"


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


def add_channel_argument(parser: argparse.ArgumentParser) -> None:
    """Add the flag that sends a run's message somewhere other than CHANNEL.

    Added through `BzCleaner.add_custom_arguments`, so a rule keeps every
    standard flag -- `--production`, `--date` -- and gains this one.
    """
    parser.add_argument(
        "--channel",
        action="store",
        default="",
        help=(
            f"Slack channel ID to post to, overriding {CHANNEL}. Useful to shake "
            "the message out somewhere else without editing the code."
        ),
    )


def versions_to_report() -> dict[str, int]:
    """The current version of each channel, with what was read written to the log.

    From the trains API rather than through `BzCleaner.init_versions`:
    `utils.get_checked_versions` returns nothing on merge day, and
    `has_enough_data` would then skip the run on exactly the day both messages
    have their own wording for.
    """
    versions = utils.get_versions_from_trains()
    logger.info(
        "Reporting Firefox %s release / %s beta / %s nightly",
        versions["release"],
        versions["beta"],
        versions["nightly"],
    )

    return versions


def post_message(
    rule: BzCleaner, channel: str, heading: str, blocks: list[dict]
) -> None:
    """Post a rule's message to Slack, or print it when the run isn't for real.

    `heading` is the message's notification fallback text, which is what a
    client that cannot render blocks shows instead of them.

    A dry run prints what it would have posted, so `--production` means here what
    it means for every other rule. `test_mode` is honoured alongside it for the
    reason `triage_owner_rotations` honours it: a test run must reach nobody.
    """
    if rule.dryrun or rule.test_mode:
        print("DRY RUN: message not posted.\n")
        for block in blocks:
            print(block_text(block))
        return

    slack.post_to_slack(channel, heading, blocks=blocks)
    logger.info("Rule %s posted to %s", rule.name(), channel)
