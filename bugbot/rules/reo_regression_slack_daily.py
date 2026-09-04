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
bugs are counted and linked like any other but never named; see
`bugbot.reo_regressions`, which also holds the open regressions query and the
posting.
"""

import datetime

from libmozdata import utils as lmdutils

from bugbot import logger, utils
from bugbot import reo_regressions as reo

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

# What this message needs back from a bug search on top of `reo.BUG_FIELDS`: it
# ages every bug, and the three timestamps it can age one from all live on the
# bug itself, so asking for them keeps it to the same one request per version.
# Still no `summary` field -- see `reo.BUG_FIELDS`.
FIELDS = f"{reo.BUG_FIELDS},assigned_to,creation_time,last_change_time,flags"
BURNDOWN_FIELDS = f"{reo.BUG_FIELDS},cf_last_resolved"


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
    - within one of reo.EXCLUDED_PRODUCTS
    - an uplift request against the channel, in any state

    All but the last of those is bugdash's Burndown list, kept in step with
    app/buglists/burndown.mjs there. Its numbering gaps at f5, f8 and f10 are
    copied along with the rest, as Bugzilla ignores unused numbers, and f9 is
    free now the product exclusions live at reo.EXCLUDED_PRODUCTS_SLOT.

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
        "classification": reo.CLASSIFICATIONS,
        "resolution": "FIXED",
        "f1": reo.status_flag(version),
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
        "f6": reo.tracking_flag(version),
        "o6": "anywordssubstr",
        "v6": "+ ? blocking",
        "f7": "CP",
        "f11": "flagtypes.name",
        "o11": "substring",
        "v11": uplift_flag,
        "n11": "1",
        **reo.without_excluded_products(),
    }


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
        bug["severity"] in reo.HIGH_SEVERITY
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
        bug["severity"] in reo.MISSING_SEVERITIES
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


def open_regressions(versions: dict[str, int]) -> list[dict]:
    """Every open release regression across the channels, each bug listed once.

    A regression affecting Nightly usually affects Beta and Release too, so the
    three queries overlap heavily: 62 hits covering 50 bugs when this was
    written. Keying on the bug id merges them, which is the point of this
    message — one list of what needs doing, not the same bug asked about three
    times. Where two channels disagree the last query wins, but the fields the
    buckets look at are all channel independent.
    """
    bugs: dict[int, dict] = {}
    for version in sorted(set(versions.values())):
        for bug in reo.fetch_bugs(reo.regressions_query(version), FIELDS):
            bugs[bug["id"]] = bug

    return list(bugs.values())


def stuck_group(bugs: list[dict], label: str, anchor: str) -> str:
    """Build the bullet and team sub-bullet for one bucket.

    Only the count and what it counts are linked; the restricted note and the age
    that follow are left as plain text, so the blue runs as far as the thing being
    claimed and no further. Building that tail here is what keeps every bullet the
    same shape, the burndown lines included.

    Empty buckets return an empty string and are left out of the message, so it
    stays a list of things to do rather than a scoreboard of zeros.

    Neither link gets a fallback query: the ageing is done here rather than by
    Bugzilla, so there is no query URL that reproduces either count.
    """
    if not bugs:
        return ""

    age = f", {reo.GREATER_THAN} {STUCK_HOURS} hours since {anchor}"

    return (
        f"• {reo.bug_link(bugs, label)}{reo.restricted_note(bugs)}{age}\n"
        f"{reo.SUB_BULLET}{reo.team_breakdown(bugs)}"
    )


def burndown_group(channel: str, version: int, cutoff: datetime.datetime) -> str:
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
        for bug in reo.fetch_bugs(query, BURNDOWN_FIELDS)
        if lmdutils.get_date_ymd(bug["cf_last_resolved"]) < cutoff
    ]
    label = f"{{}} Fx{version} {channel.title()} fixed with no uplift request"

    return stuck_group(bugs, label, "resolved")


class ReoRegressionSlackDaily(reo.ReoRegressionsRule):
    """Post the release regressions that are waiting on somebody to Slack.

    No `must_run`: this one runs every day the cron script invokes it, which is
    every weekday.
    """

    def description(self) -> str:
        return "REO release regressions needing action posted to Slack"

    def heading(self) -> str:
        return HEADING

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
        bugs = open_regressions(versions)

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

            if group := burndown_group(channel, version, cutoff):
                groups.append(group)

        sections.extend(groups or [NOTHING_STUCK])

        return titles + reo.to_blocks(sections)


if __name__ == "__main__":
    ReoRegressionSlackDaily().run()
