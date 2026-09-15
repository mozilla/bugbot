# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime

from bugbot import reo_regressions as reo
from bugbot import utils
from bugbot.rules import reo_regression_slack_daily as daily
from bugbot.rules.reo_regression_slack_daily import ReoRegressionSlackDaily


def test_the_rule_is_named_after_its_module():
    assert ReoRegressionSlackDaily().name() == "reo_regression_slack_daily"


def test_the_daily_message_is_ungated():
    # Every weekday the cron script invokes it: these are things somebody has to
    # do, so a day skipped is a day nobody was asked. The summary is the one with
    # a `must_run` in configs/rules.json.
    rule = ReoRegressionSlackDaily()
    monday = datetime.datetime(2026, 8, 31)

    assert utils.get_config("reo_regression_slack_daily", "must_run") is None
    assert all(rule.must_run(monday + datetime.timedelta(days=day)) for day in range(7))


def test_the_burndown_query_drops_the_excluded_products():
    query = daily.burndown_query(150, "approval-mozilla-beta")
    excluded = {
        query[f"v{n}"]
        for n in range(
            reo.EXCLUDED_PRODUCTS_SLOT,
            reo.EXCLUDED_PRODUCTS_SLOT + len(reo.EXCLUDED_PRODUCTS),
        )
        if query.get(f"f{n}") == "product"
    }

    assert excluded == set(reo.EXCLUDED_PRODUCTS)


def test_uplift_flags_come_from_get_flag():
    for channel in daily.UPLIFT_CHANNELS:
        query = daily.burndown_query(150, utils.get_flag(None, "approval", channel))
        assert query["v11"] == f"approval-mozilla-{channel}"


def test_burndown_query_qualifies_security_bugs():
    query = daily.burndown_query(150, "approval-mozilla-beta")

    # The f2-f7 OR group narrows "still marked affected" down to "worth chasing an
    # uplift for", and being a security bug is one of the three ways in. It is not
    # an access filter: it only started matching anything once bugbot's key made
    # those bugs visible in the first place.
    assert query["j2"] == "OR"
    assert (query["f4"], query["o4"], query["v4"]) == ("bug_group", "substring", "sec")
    assert (query["f2"], query["f7"]) == ("OP", "CP")

    # The uplift request is negated, so what is left is the fixes nobody has asked
    # to uplift.
    assert query["v11"] == "approval-mozilla-beta"
    assert query["n11"] == "1"


def test_every_search_asks_for_the_groups_field():
    # Without it no message can tell a restricted bug from a public one.
    for fields in (daily.FIELDS, daily.BURNDOWN_FIELDS):
        assert "groups" in fields.split(",")


def test_no_search_asks_for_a_bug_summary():
    # Extending `reo.BUG_FIELDS` must not be what quietly starts naming restricted
    # bugs.
    for fields in (daily.FIELDS, daily.BURNDOWN_FIELDS):
        assert "summary" not in fields.split(",")


def test_the_ageing_fields_are_asked_for():
    # Each bucket ages a bug from a different timestamp, and all of them come back
    # on the bug itself, which is what keeps this to one request per version.
    assert {"creation_time", "last_change_time", "flags"} <= set(
        daily.FIELDS.split(",")
    )
    assert "cf_last_resolved" in daily.BURNDOWN_FIELDS.split(",")


def test_stuck_group_puts_the_note_outside_the_link_and_before_the_age(monkeypatch):
    monkeypatch.setattr(reo, "team_of", lambda bug: "Team A")
    bugs = [
        {"id": 1, "groups": ["core-security-release"]},
        {"id": 2, "groups": []},
    ]

    bullet, sub_bullet = daily.stuck_group(bugs, "{} S2+ unassigned", "filed").split(
        "\n"
    )

    assert bullet == (
        "• <https://bugzilla.mozilla.org/buglist.cgi?bug_id=1,2&order=bug_list"
        "|2 S2+ unassigned> (1 restricted), &gt; 24 hours since filed"
    )
    # The note belongs to the top-level bullet alone; repeated on the team line it
    # would crowd out the counts that line exists for.
    assert "restricted" not in sub_bullet


def test_stuck_group_leaves_out_an_empty_bucket():
    assert daily.stuck_group([], "{} S2+ unassigned", "filed") == ""


def test_bucket_predicates_read_bugzillas_trailing_z():
    # Bugzilla stamps its timestamps with a Z, which `datetime.fromisoformat`
    # only learned to read in 3.11 while bugbot still supports 3.10. Ageing goes
    # through libmozdata, which has always read it, and this pins that.
    cutoff = datetime.datetime(2026, 8, 17, tzinfo=datetime.timezone.utc)
    bug = {
        "severity": "S2",
        "product": "Core",
        "component": "Layout",
        "assigned_to": "nobody@mozilla.org",
        "creation_time": "2026-08-16T23:40:15Z",
    }

    assert daily.needs_assignee(bug, cutoff)
    assert not daily.needs_assignee(
        {**bug, "creation_time": "2026-08-18T00:00:00Z"}, cutoff
    )


def test_unassigned_uses_the_shared_helper():
    # utils.is_no_assignee, so a component's `.bugs` default counts as unassigned
    # the way it does everywhere else in bugbot.
    cutoff = datetime.datetime(2026, 8, 17, tzinfo=datetime.timezone.utc)
    bug = {
        "severity": "S2",
        "product": "Core",
        "component": "Layout",
        "creation_time": "2026-08-16T23:40:15Z",
    }

    assert daily.needs_assignee({**bug, "assigned_to": "nobody@mozilla.org"}, cutoff)
    assert daily.needs_assignee({**bug, "assigned_to": "gfx-bugs@mozilla.bugs"}, cutoff)
    assert daily.needs_assignee({**bug, "assigned_to": ""}, cutoff)
    assert not daily.needs_assignee(
        {**bug, "assigned_to": "someone@mozilla.com"}, cutoff
    )
