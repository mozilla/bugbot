# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Post the REO release regressions that need action to Slack.

The same bug set as the cycle summary, `reo_regression_slack`, with the three
channels merged into one deduplicated list and only the bugs stuck long enough
to need a nudge: high severity with nobody on them, no severity decision, or an
unanswered needinfo. It ends with bugdash's Burndown list per version, Beta and
Release only, cut down to the fixes nobody has asked to uplift. Each line is
broken down by owning team.

Posted every weekday, unlike the summary: these are things somebody has to do,
so a day skipped is a day nobody was asked.
"""

import argparse
import datetime
import functools
from typing import Any

from libmozdata import utils as lmdutils

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

# Above every slot either query uses.
EXCLUDED_PRODUCTS_SLOT = 12

UNKNOWN_TEAM = "Unknown team"

# A Slack section block holds at most 3000 characters.
SECTION_LIMIT = 3000

# Above this length a snapshot URL is shortened; see `bug_link`.
MAX_SNAPSHOT_URL = 2000

# Slack renders this back as >. The bare character ends a link's label and opens
# a blockquote at the start of a line.
GREATER_THAN = "&gt;"

# Slack has no nested lists in message text, so indent sub-bullets by hand.
SUB_BULLET = "    ◦ "

# `groups` is how a bug is known to be restricted. No `summary`: the message
# names no bug, so restricted ones are counted and linked but never named.
BUG_FIELDS = "id,severity,product,component,groups"

# What each query adds on top: whatever its buckets age a bug from.
FIELDS = f"{BUG_FIELDS},assigned_to,creation_time,last_change_time,flags"
BURNDOWN_FIELDS = f"{BUG_FIELDS},cf_last_resolved"

# Left out of the "S2+ unassigned" bucket alone. Empty today, as the one
# exemption we have belongs to a component rather than to a whole product.
UNASSIGNED_EXEMPT_PRODUCTS: tuple[str, ...] = ()

# Web Compatibility::Site Reports bugs S2 definition does not follow the
# regression severity definition. The exemption is the component's, not the
# product's, and applies to this one bucket only.
UNASSIGNED_EXEMPT_COMPONENTS = ("Site Reports",)

# Bugs are aged from a fixed point in the past rather than over a window, so one
# that went stale on Friday is still in Monday's message.
STUCK_HOURS = 24

# The channels a fix only reaches by being uplifted, in the order the burndown
# lines appear. Nightly is where fixes land, so it needs no line.
UPLIFT_CHANNELS = ("beta", "release")

# Also the message's fallback text, which is what notification previews show.
HEADING = "Action needed: REO release regressions"

CADENCE = "Daily update"

INTRO = (
    "These release regressions are waiting on activity and fall into the urgent "
    "category. "
    f"They have been pending for longer than {STUCK_HOURS} hours. "
    "Please take a look where one of your teams is listed."
)

# So a quiet day reads as good news rather than as the script having failed.
NOTHING_STUCK = "•  Nothing needs attention"


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


def regressions_query(version: int) -> dict:
    """Build the open regressions query for a version.

    Bugs with all of the following:
    - regression keyword
    - open (unresolved)
    - status-firefox{version} is affected
    Bugs with any of the following are ignored:
    - tracking-firefox{version} is -
    - stalled or intermittent-failure keywords
    - within one of EXCLUDED_PRODUCTS

    The cycle summary splits this set into the bugs that regressed during the
    cycle and the ones that were already there; this message wants the whole set.

    The gaps in the chart numbering come from bugdash and from that split, and
    are harmless: Bugzilla ignores unused numbers.
    """
    return {
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


def burndown_query(version: int, uplift_flag: str) -> dict:
    """Build the burndown query for a version, less the bugs already asking to uplift.

    Bugs with all of the following:
    - resolved as fixed
    - status-firefox{version} is affected or fix-optional
    - any of:
      - crash, regression, leak, topcrash, assertion or dataloss keywords
      - in a security group
      - tracking-firefox{version} is +, ? or blocking
    Bugs with any of the following are ignored:
    - within one of EXCLUDED_PRODUCTS
    - an uplift request against the channel, in any state

    All but the last of those is bugdash's Burndown list, kept in step with
    app/buglists/burndown.mjs there, its gaps in the chart numbering included.

    The uplift request is a flag on an attachment, so it is left to Bugzilla
    rather than filtered here: flagtypes.name matches attachment flags too, and
    matching the bare name catches the request in any state. n11 negates that.
    """
    return {
        "classification": CLASSIFICATIONS,
        "resolution": "FIXED",
        "f1": utils.get_flag(version, "status", "release"),
        "o1": "anywords",
        "v1": "affected optional",
        "j2": "OR",
        "f2": "OP",
        "f3": "keywords",
        "o3": "anywords",
        "v3": "crash regression leak topcrash assertion dataloss",
        "f4": "bug_group",
        "o4": "substring",
        "v4": "sec",
        "f6": utils.get_flag(version, "tracking", "release"),
        "o6": "anywordssubstr",
        "v6": "+ ? blocking",
        "f7": "CP",
        "f11": "flagtypes.name",
        "o11": "substring",
        "v11": uplift_flag,
        "n11": "1",
        **without_excluded_products(),
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


def bug_link(bugs: list[dict], label_template: str) -> str:
    """Format a non-empty bug list as a Slack link labelled with its count.

    An over-long snapshot URL is shortened, and failing that the count is left
    unlinked. No line here has a live query to fall back on, as the ageing is done
    in this rule rather than by Bugzilla.
    """
    label = label_template.format(len(bugs))
    snapshot = snapshot_url(bugs)

    if len(snapshot) <= MAX_SNAPSHOT_URL:
        return f"<{snapshot}|{label}>"

    url = shortened_url(snapshot)
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
    looks shorter than the count to a reader without access. That is a wider test
    than the `bug_group ~ "sec"` branch in `burndown_query`, which asks whether a
    fix is worth chasing rather than whether the bug is readable.
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


def stuck_since() -> datetime.datetime:
    """The moment a bug has to predate to count as stuck. See STUCK_HOURS."""
    now = datetime.datetime.now(datetime.timezone.utc)

    return now - datetime.timedelta(hours=STUCK_HOURS)


def unassigned_exempt(bug: dict) -> bool:
    """Whether a bug is exempt from the S2+ unassigned bucket."""
    return (
        bug["product"] in UNASSIGNED_EXEMPT_PRODUCTS
        or bug["component"] in UNASSIGNED_EXEMPT_COMPONENTS
    )


def needs_assignee(bug: dict, cutoff: datetime.datetime) -> bool:
    """A high severity bug nobody has taken on, aged from when it was filed.

    `utils.is_no_assignee` is wider than the REO queries take it, which count a
    bug parked on a component default address as assigned, so this can flag a bug
    bugdash would not.
    """
    return (
        bug["severity"] in HIGH_SEVERITY
        and not unassigned_exempt(bug)
        and utils.is_no_assignee(bug["assigned_to"])
        and lmdutils.get_date_ymd(bug["creation_time"]) < cutoff
    )


def needs_severity(bug: dict, cutoff: datetime.datetime) -> bool:
    """A bug still waiting on a severity decision, aged from its last activity.

    Any change counts as activity, not just a triage one, so a bug someone is
    asking questions on is left out until it goes quiet again.
    """
    return (
        bug["severity"] in MISSING_SEVERITIES
        and lmdutils.get_date_ymd(bug["last_change_time"]) < cutoff
    )


def needs_answer(bug: dict, cutoff: datetime.datetime) -> bool:
    """A bug with a needinfo nobody has answered, aged from when it was asked.

    Several open requests still only count the bug once. Aged from the flag's
    creation_date, which is when the request now standing was made, so one asked
    again after an answer is aged from the second ask.
    """
    return any(
        lmdutils.get_date_ymd(flag["creation_date"]) < cutoff
        for flag in utils.get_needinfo(bug)
    )


# What makes a bug belong in a bucket, the label its count goes in, and what its
# age is counted from. A bug can be in more than one. Each names its own anchor
# because each is aged from a different timestamp.
STUCK_BUCKETS = (
    (needs_assignee, "{} S2+ unassigned", "filed"),
    (needs_severity, "{} missing severity", "last change"),
    (needs_answer, "{} needinfo pending", "requested"),
)


def stuck_group(bugs: list[dict], label: str, anchor: str) -> str:
    """Build the bullet and team sub-bullet for one bucket.

    Only the count and what it counts are linked; the restricted note and the age
    that follow are plain text. Empty buckets return an empty string and are left
    out of the message.
    """
    if not bugs:
        return ""

    age = f", {GREATER_THAN} {STUCK_HOURS} hours since {anchor}"

    return (
        f"• {bug_link(bugs, label)}{restricted_note(bugs)}{age}\n"
        f"{SUB_BULLET}{team_breakdown(bugs)}"
    )


class ReoRegressionSlackDaily(BzCleaner):
    """A `BzCleaner` that reports to Slack instead of by email.

    No `must_run` in `configs/rules.json`: this runs every day the cron invokes it.
    """

    # Overridden by a `--channel` run, so this is the channel the cron posts to.
    channel = CHANNEL

    def description(self) -> str:
        return "REO release regressions needing action posted to Slack"

    def all_include_fields(self) -> bool:
        # `BzCleaner` would otherwise add `summary` to every query.
        return True

    def has_default_products(self) -> bool:
        # Scoped by classification instead, as bugdash's queries are.
        return False

    def filter_no_nag_keyword(self) -> bool:
        # [no-nag] is a request not to mail a bug's assignee. This message names
        # teams rather than people and is read by the release managers chasing
        # the work, so dropping those bugs would hide work still to be done.
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

    def fetch_bugs(self, query: dict, fields: str = FIELDS) -> list[dict]:
        """Run one of this rule's queries through `BzCleaner`'s search path.

        One query per version plus one per burndown line, each set here and read
        back by `get_bz_params`, the way `warn_regressed_by` steps through its
        two. libmozdata only pages a query carrying none of count_only, limit,
        order or offset, so no query here may add one.
        """
        self.params = {**query, "include_fields": fields}

        return list(self.get_bugs().values())

    def open_regressions(self, versions: dict[str, int]) -> list[dict]:
        """Every open release regression across the channels, each bug listed once.

        The three queries overlap heavily. Where they disagree the last one wins,
        but the fields the buckets look at are all channel independent.
        """
        bugs: dict[int, dict] = {}
        for version in sorted(set(versions.values())):
            for bug in self.fetch_bugs(regressions_query(version)):
                bugs[bug["id"]] = bug

        return list(bugs.values())

    def burndown_group(
        self, channel: str, version: int, cutoff: datetime.datetime
    ) -> str:
        """Build the burndown bullet for one channel, aged from when each bug was fixed.

        Per version rather than merged across the channels: a fix reaches Beta and
        Release by separate uplifts, so the same bug can be outstanding on one and
        done on the other.
        """
        query = burndown_query(version, utils.get_flag(None, "approval", channel))
        bugs = [
            bug
            for bug in self.fetch_bugs(query, BURNDOWN_FIELDS)
            if lmdutils.get_date_ymd(bug["cf_last_resolved"]) < cutoff
        ]
        label = f"{{}} Fx{version} {channel.title()} fixed with no uplift request"

        return stuck_group(bugs, label, "resolved")

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
        # Not `init_versions`: `utils.get_checked_versions` returns nothing on
        # merge day, which this message has wording for.
        self.post_message(self.blocks(utils.get_versions_from_trains()))

        return []

    def blocks(self, versions: dict[str, int]) -> list[dict]:
        """Build the action required message, one section per bucket.

        Header blocks take plain text only, which is why the cadence is a separate
        context block.
        """
        titles: list[dict] = [
            {"type": "header", "text": {"type": "plain_text", "text": HEADING}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": CADENCE}]},
        ]
        sections = [INTRO]

        cutoff = stuck_since()
        bugs = self.open_regressions(versions)

        groups = [
            group
            for matches, label, anchor in STUCK_BUCKETS
            if (
                group := stuck_group(
                    [bug for bug in bugs if matches(bug, cutoff)], label, anchor
                )
            )
        ]
        for channel in UPLIFT_CHANNELS:
            version = versions.get(channel)
            if version is None:
                # Skipped rather than raised, so adding a channel above can never
                # be the thing that costs the whole message.
                logger.warning("No version for %s; skipping its burndown line", channel)
                continue

            if group := self.burndown_group(channel, version, cutoff):
                groups.append(group)

        sections.extend(groups or [NOTHING_STUCK])

        return titles + to_blocks(sections)


if __name__ == "__main__":
    ReoRegressionSlackDaily().run()
