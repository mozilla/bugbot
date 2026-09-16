# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Post the REO release regressions that need action to Slack.

The same bug set as the cycle summary, `reo_regression_slack`, with the new and
carry over split dropped and the three channels merged into one deduplicated
list, reporting only the bugs stuck long enough to need a nudge: high severity
with nobody on them (UNASSIGNED_EXEMPT_* exempt), no severity decision, or an
unanswered needinfo. It ends with bugdash's Burndown list per version, Beta and
Release only, cut down to the fixes nobody has asked to uplift. Each line is
broken down by owning team.

Posted every weekday the cron script invokes it, unlike the summary: these are
things somebody has to do, so a day skipped is a day nobody was asked.

Every count links to a Bugzilla list of exactly the bugs counted. Restricted
bugs are counted in the totals and included in the links like any other, but
never named: no message prints a bug summary, which is the same line
`BzCleaner.get_summary` draws. The top-level bullet says how many of its count
are restricted, because a reader without access opens the link and finds a
shorter list than the number they clicked on. See `restricted_note`.
"""

import argparse
import datetime
import functools
from typing import Any

from libmozdata import utils as lmdutils

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
# message and none of the burndown lines.
#
# Not the `exclude_products` key some rules carry in `configs/rules.json`: that one
# subtracts from `BzCleaner`'s default product list, which these classification
# scoped queries never use, so the name would mean something different here.
EXCLUDED_PRODUCTS = ("Testing", "Developer Infrastructure")

# Where the product exclusions are numbered from in a boolean chart. Above every
# slot either query uses -- `regressions_query` and `burndown_query`.
EXCLUDED_PRODUCTS_SLOT = 12

# For a component with no team_name, or one missing from the mapping entirely.
# Every component had a team when this was written, so this is only a guard
# against silently dropping bugs out of the per-team line.
UNKNOWN_TEAM = "Unknown team"

# A Slack section block holds at most 3000 characters.
SECTION_LIMIT = 3000

# Above this length a snapshot URL is shortened, and failing that dropped
# entirely -- see `bug_link`. Keeps one very long bug list from pushing a section
# over SECTION_LIMIT.
MAX_SNAPSHOT_URL = 2000

# Slack renders this back as >. Sending the character itself would work where it
# is used now, but it ends a link's label at the first > and opens a blockquote at
# the start of a line, so a label or bullet reworded around it would break in ways
# that are easy to miss. The entity is never wrong.
GREATER_THAN = "&gt;"

# Slack has no nested lists in message text, so indent sub-bullets by hand.
# Four plain spaces; if Slack ever collapses them, non-breaking spaces (U+00A0)
# are the fix.
SUB_BULLET = "    ◦ "

# Products where an unassigned high severity bug is not something to nag about,
# so they are left out of the "S2+ unassigned" bucket alone. Empty today, as the
# one exemption we have belongs to a component rather than to a whole product;
# kept so exempting a product later is a one line change.
UNASSIGNED_EXEMPT_PRODUCTS: tuple[str, ...] = ()

# The same, per component: Web Compatibility::Site Reports bugs S2 definition
# does not follow the regression severity definition. The exemption is the
# component's, not the product's — Site Reports only happens to sit under Web
# Compatibility, and the rest of that product still follows the definition.
#
# Matched on the component name alone, exactly as Bugzilla reports it, and only
# against this one bucket: an exempt bug with no severity or an unanswered
# needinfo is still stuck in the way those buckets mean.
UNASSIGNED_EXEMPT_COMPONENTS = ("Site Reports",)

# How long a bug has to have been stuck before this message nags about it.
# Long enough that a bug filed or touched during yesterday's working day is left
# alone, short enough that nothing sits unnoticed for a second day.
#
# It ages bugs from a fixed point in the past rather than over a window, so a
# quiet weekend doesn't hide anything: a bug that went stale on Friday is still
# in Monday's message, and stays there until someone acts on it.
STUCK_HOURS = 24

# The channels a fix has to be uplifted to reach. A fix only reaches Beta or
# Release by being uplifted, so a burndown bug with no uplift request against the
# channel is a fix that will not ship in the version it is marked as affecting.
#
# The flag is matched by name alone, so any state of it counts as asked: pending
# (?), granted (+) and denied (-) alike. Matching only a pending request would
# put a bug back on the list the moment its uplift was approved, since the flag
# stops being pending then and the fix has yet to land, and would keep a denied
# one on the list for good.
#
# Nightly is where fixes land, so it needs no uplift and gets no burndown line.
# The order here is the order the lines appear in.
#
# A channel added here also needs a version from `utils.get_versions_from_trains()`.
# One without a version is skipped with a note in the log rather than reported.
#
# The flag name itself is built by `utils.get_flag`, so this is only the list of
# channels. That is also what makes ESR addable: its flag embeds the version
# number, which `get_flag` knows how to format and a constant here could not.
UPLIFT_CHANNELS = ("beta", "release")

# The title leads with what makes this message different from the twice weekly
# status summary, rather than trailing it. Slack cuts a long title off in
# notification previews and the eye reads from the left, so a title starting
# "REO release regression" like the other one would be indistinguishable at a
# glance. It is also the fallback text of the message, which is what those
# previews show.
#
# Slack allows 150 characters in a header block, which this is nowhere near.
HEADING = "Action needed: REO release regressions"

# Sits under the heading in a context block: small, grey, and read as a label on
# the message rather than as part of it. Says the message is a recurring one, so
# a reader who has not seen it before knows it is not an incident.
CADENCE = "Daily update"

# Follows the heading. Says the one thing every line below has in common, so the
# bullets don't each have to explain themselves, and points each team at the
# sub-bullets, which is where the message asks anything of anyone.
#
# What the buckets share is that none of them is waiting on the work: each is
# waiting on an action, which is what makes the message worth sending daily and
# what separates it from the twice weekly summary of how the cycle is going.
#
# The age is given here as a round number and again on each bullet, where it is
# also said what the age is counted from, as that differs per bucket.
INTRO = (
    "These release regressions are waiting on activity and fall into the urgent "
    "category. "
    f"They have been pending for longer than {STUCK_HOURS} hours. "
    "Please take a look where one of your teams is listed."
)

# Shown on a day where every bucket came out empty, so a quiet day reads as good
# news rather than as the script having failed.
NOTHING_STUCK = "•  Nothing needs attention"

# What a bug search has to come back with for this message: it ages every bug,
# and the three timestamps it can age one from all live on the bug itself, so
# asking for them keeps it to the same one request per version.
#
# `groups` is how a bug is known to be restricted, and the message counts those.
# See `restricted_note`.
#
# No `summary` field, in either of these. That is the line this message does not
# cross, and the same one `BzCleaner.get_summary` draws.
BUG_FIELDS = "id,severity,product,component,groups"
FIELDS = f"{BUG_FIELDS},assigned_to,creation_time,last_change_time,flags"
BURNDOWN_FIELDS = f"{BUG_FIELDS},cf_last_resolved"


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
    cycle and the ones that were already there; this message wants the whole set,
    so it has no equivalent of that condition.

    Nothing here filters on `bug_group`: an authenticated search returns every bug
    the key can see, so restricted regressions arrive on their own.

    Field numbering is Bugzilla's boolean charts: f/o/v are the field, operator
    and value for a numbered condition, OP and CP open and close a group, j sets
    how a group joins (OR here, AND otherwise) and n negates. The gaps at f2-f7
    and f9 are harmless, as Bugzilla ignores unused numbers: f7 comes from
    bugdash, f2-f6 are where the cycle summary puts its split, and f9 is free now
    the product exclusions live at EXCLUDED_PRODUCTS_SLOT.
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
    app/buglists/burndown.mjs there. Its numbering gaps at f5, f8 and f10 are
    copied along with the rest, as Bugzilla ignores unused numbers, and f9 is
    free now the product exclusions live at EXCLUDED_PRODUCTS_SLOT.

    The f3-f7 group is what narrows "every fix still marked affected" down to the
    fixes worth chasing an uplift for, and being a security bug is one of the three
    ways in. It is a test of whether a bug qualifies, not of whether we can see it:
    under anonymous queries that branch matched nothing, because a search never
    returns a bug the requester cannot read, so it only starts contributing here.
    What it adds is the fixed security bugs carrying none of those keywords and no
    tracking flag — a population that would otherwise fall off the burndown despite
    being perfectly visible.

    The uplift request is a flag on an attachment, and the only way a bug search
    will report those is to send back every attachment with it, so it is left to
    Bugzilla rather than filtered here. flagtypes.name matches the flags on a
    bug's attachments as well as those on the bug itself, on name and state
    together, so matching the bare name catches the request whatever became of
    it. n11 negates that, leaving the fixes nobody has asked to uplift.
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


def bug_link(bugs: list[dict], label_template: str) -> str:
    """Format a non-empty bug list as a Slack link labelled with its count.

    label_template is formatted with the count, e.g. "{} S2+ unassigned".

    A snapshot URL that comes out too long is shortened, which keeps the link
    pointing at exactly the bugs counted, and failing that the count is left
    unlinked. No line here has a live query to fall back on: the ageing is done
    in this rule rather than by Bugzilla, and reproducing a team as a query means
    listing all its components.

    Callers are expected to skip empty lists: an empty bug_id would link to a
    broken list, and a count of zero is left out of the message anyway.
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
    partner group just as it does for `core-security`. That is a wider test than
    the `bug_group ~ "sec"` branch in `burndown_query`, which is asking a
    different question — whether a fix is worth chasing, not whether it is
    readable.

    Deliberately plain text rather than part of the link label, so the blue runs as
    far as the thing being counted and no further, and deliberately only used on the
    top-level bullets: repeated on every team sub-bullet it would say little and
    crowd out the counts that are the point of those lines.
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
    means a busier day can't start splitting the message again.

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


def stuck_since() -> datetime.datetime:
    """The moment a bug has to predate to count as stuck. See STUCK_HOURS."""
    now = datetime.datetime.now(datetime.timezone.utc)

    return now - datetime.timedelta(hours=STUCK_HOURS)


def unassigned_exempt(bug: dict) -> bool:
    """Whether a bug is exempt from the S2+ unassigned bucket.

    Exempt by product or by component, so either can be exempted on its own
    without the other having to be named.
    """
    return (
        bug["product"] in UNASSIGNED_EXEMPT_PRODUCTS
        or bug["component"] in UNASSIGNED_EXEMPT_COMPONENTS
    )


def needs_assignee(bug: dict, cutoff: datetime.datetime) -> bool:
    """A high severity bug nobody has taken on, aged from when it was filed.

    What counts as unassigned is `utils.is_no_assignee`, shared with the rest of
    bugbot: the nobody@ placeholder, a component's `.bugs` default address, or no
    assignee at all. That last pair is wider than the REO queries take it — they
    count a bug parked on a component default as assigned — so this can flag a bug
    bugdash would not. Nothing differed on the day it changed, but that is a fact
    about that day's bug set rather than a guarantee.

    Exempt bugs are left out: an unassigned bug there is not a bug that has been
    overlooked. See unassigned_exempt().
    """
    return (
        bug["severity"] in HIGH_SEVERITY
        and not unassigned_exempt(bug)
        and utils.is_no_assignee(bug["assigned_to"])
        and lmdutils.get_date_ymd(bug["creation_time"]) < cutoff
    )


def needs_severity(bug: dict, cutoff: datetime.datetime) -> bool:
    """A bug still waiting on a severity decision, aged from its last activity.

    Any change to the bug counts as activity, not just a triage one, so a bug
    with activity is left out until it goes quiet again. There are some limitations
    with this approach since the activity may be from someone outside the triage
    team asking questions or adjusting metadata.
    """
    return (
        bug["severity"] in MISSING_SEVERITIES
        and lmdutils.get_date_ymd(bug["last_change_time"]) < cutoff
    )


def needs_answer(bug: dict, cutoff: datetime.datetime) -> bool:
    """A bug with a needinfo nobody has answered, aged from when it was requested.

    What counts as an open request is left to `utils.get_needinfo`, so this agrees
    with every other rule that nags about one. The ageing is not: `get_needinfo`
    filters on modification_date in whole days, and a flag's creation_date is when
    the request now standing was made, so one that was answered and then asked again
    is aged from the second ask rather than the first.

    Several open requests on one bug still only count the bug once, and the oldest
    of them is what decides.
    """
    return any(
        lmdutils.get_date_ymd(flag["creation_date"]) < cutoff
        for flag in utils.get_needinfo(bug)
    )


# The buckets, in the order they appear in the message: what makes a bug belong
# in one, the label its count goes in, and what its age is counted from. A bug
# can be in more than one, as they describe different things left undone rather
# than a state it is in.
#
# Every bucket names its own anchor because each is aged from a different
# timestamp. Left unsaid, the same "> 24 hours" on every bullet reads as one
# shared deadline, when a bug filed weeks ago and one that went quiet yesterday
# are being asked about for different reasons.
STUCK_BUCKETS = (
    (needs_assignee, "{} S2+ unassigned", "filed"),
    (needs_severity, "{} missing severity", "last change"),
    (needs_answer, "{} needinfo pending", "requested"),
)


def stuck_group(bugs: list[dict], label: str, anchor: str) -> str:
    """Build the bullet and team sub-bullet for one bucket.

    Only the count and what it counts are linked; the restricted note and the age
    that follow are left as plain text, so the blue runs as far as the thing being
    claimed and no further. Building that tail here is what keeps every bullet the
    same shape, the burndown lines included.

    Empty buckets return an empty string and are left out of the message, so it
    stays a list of things to do rather than a scoreboard of zeros.
    """
    if not bugs:
        return ""

    age = f", {GREATER_THAN} {STUCK_HOURS} hours since {anchor}"

    return (
        f"• {bug_link(bugs, label)}{restricted_note(bugs)}{age}\n"
        f"{SUB_BULLET}{team_breakdown(bugs)}"
    )


class ReoRegressionSlackDaily(BzCleaner):
    """Post the release regressions that are waiting on somebody to Slack.

    A `BzCleaner` that reports to Slack instead of by email: the searches, the
    arguments and the error handling are all the framework's, and
    `get_email_data` posts the message and returns nothing to mail.

    No `must_run` entry in `configs/rules.json`: this one runs every day the
    cron script invokes it, which is every weekday. The twice weekly summary,
    `reo_regression_slack`, is the one with a cadence of its own.
    """

    # Where the message goes. A `--channel` run overrides it, so this is the
    # channel the cron posts to; see `parse_custom_arguments`.
    channel = CHANNEL

    def description(self) -> str:
        return "REO release regressions needing action posted to Slack"

    def all_include_fields(self) -> bool:
        # The fields a search asks for are FIELDS and BURNDOWN_FIELDS and
        # nothing else. `BzCleaner` would otherwise add `summary` to every
        # query, which is the one field this message does not print.
        return True

    def has_default_products(self) -> bool:
        # Both queries are scoped by classification, as bugdash's are; the
        # default product list would report a different bug set.
        return False

    def filter_no_nag_keyword(self) -> bool:
        # [no-nag] is a request not to mail a bug's assignee about it. This
        # message names teams rather than people and is read by the release
        # managers chasing the work, so dropping those bugs would hide work
        # that still has to be done.
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
        table, its summary included. This message ages every bug and counts it,
        so it needs the fields it asked for and none of the rest.
        """
        data[str(bug["id"])] = bug

    def fetch_bugs(self, query: dict, fields: str = FIELDS) -> list[dict]:
        """Run one of this rule's queries through `BzCleaner`'s search path.

        Several queries per run -- one per version, plus one per burndown line
        -- each one set here and read back by `get_bz_params`, the way
        `warn_regressed_by` steps through its two. Going through `get_bugs` is
        what attaches bugbot's API key, which is the whole reason this sees
        restricted bugs, along with the query timeout and the paging. libmozdata
        pages a search itself -- counting first, then walking the results in
        chunks -- but only for a query carrying none of count_only, limit, order
        or offset, so no query here may add one.
        """
        self.params = {**query, "include_fields": fields}

        return list(self.get_bugs().values())

    def open_regressions(self, versions: dict[str, int]) -> list[dict]:
        """Every open release regression across the channels, each bug listed once.

        A regression affecting Nightly usually affects Beta and Release too, so
        the three queries overlap heavily: 62 hits covering 50 bugs when this
        was written. Keying on the bug id merges them, which is the point of
        this message — one list of what needs doing, not the same bug asked
        about three times. Where two channels disagree the last query wins, but
        the fields the buckets look at are all channel independent.
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

        Unlike the other buckets this is per version rather than merged across the
        channels: a fix reaches Beta and Release by separate uplifts, so the same bug
        can be outstanding on one and done on the other, and each has to be asked for
        against its own version.

        Nothing is subtracted for a bug fixed in the version's own cycle, as the
        query only keeps bugs the version is still marked as affected by. Once a fix
        is uplifted the status goes to fixed and the bug leaves the list.
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
        """Build the action required message, one section per bucket.

        A header block titles the message and a context block labels it, then the
        standing ask and each bucket that has anything in it follow as sections.

        The title is a header rather than bold text in a section so that it
        renders at heading weight and separates the ask from the list. Header
        blocks take plain text only, which is why nothing else lives in there.
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
                # A channel with no version to query. Skipped rather than raised,
                # so adding a channel above can never be the thing that costs the
                # whole message, and said out loud so it isn't a silent no-op
                # either.
                #
                # ESR is the case that will turn up. `get_versions_from_trains`
                # reports an esr version and `utils.get_flag` formats its numbered
                # approval flag, so adding it here is now only a question of
                # whether we want the line, not of whether the name can be built.
                logger.warning("No version for %s; skipping its burndown line", channel)
                continue

            if group := self.burndown_group(channel, version, cutoff):
                groups.append(group)

        sections.extend(groups or [NOTHING_STUCK])

        return titles + to_blocks(sections)


if __name__ == "__main__":
    ReoRegressionSlackDaily().run()
