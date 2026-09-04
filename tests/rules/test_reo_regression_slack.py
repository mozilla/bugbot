# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime

from bugbot import reo_regressions as reo
from bugbot import utils
from bugbot.rules.reo_regression_slack import ReoRegressionSlack, regression_group


def test_the_rule_is_named_after_its_module():
    # Which is what `logger_extra["bugbot_rule"]` is tagged with, so a failure in
    # this message is told apart from one in the daily message.
    assert ReoRegressionSlack().name() == "reo_regression_slack"


def test_the_summary_runs_on_monday_and_thursday_only():
    rule = ReoRegressionSlack()
    monday = datetime.date(2026, 8, 31)
    week = [monday + datetime.timedelta(days=day) for day in range(7)]

    assert [day for day in week if rule.must_run(day)] == [
        monday,
        datetime.date(2026, 9, 3),  # Thursday
    ]


def test_the_cadence_is_the_rules_own():
    # In the rule rather than in configs/rules.json, the way `missed_uplifts` and
    # `workflow.p2_merge_day` decide their days, so a config entry can neither add
    # a day nor take one away.
    assert utils.get_config("reo_regression_slack", "must_run", None) is None
    assert not ReoRegressionSlack().must_run(datetime.date(2026, 9, 1))  # Tuesday


def test_regression_group_notes_restricted_bugs_on_the_top_line_only(monkeypatch):
    bugs = [
        {"id": 1, "severity": "S2", "groups": ["core-security-release"]},
        {"id": 2, "severity": "--", "groups": []},
    ]
    monkeypatch.setattr(reo, "fetch_bugs", lambda query, fields=None: bugs)
    monkeypatch.setattr(reo, "team_of", lambda bug: "Team A")

    bullet, teams, severities = regression_group(150, False, "New", by_team=True).split(
        "\n"
    )

    assert bullet.endswith("|2 New Regressions> (1 restricted)")
    assert "restricted" not in teams
    assert "restricted" not in severities
    assert "1 S2+" in severities
    assert "1 missing severity" in severities


def test_force_bypasses_the_must_run_gate():
    parser = ReoRegressionSlack().get_args_parser()

    assert not parser.parse_args([]).force
    assert parser.parse_args(["--force"]).force


def test_the_channel_is_a_constant_the_flag_can_override():
    parser = ReoRegressionSlack().get_args_parser()

    # No flag means the module constant, which is what the cron runs with.
    assert parser.parse_args([]).channel == ""
    assert parser.parse_args(["--channel", "C_TEST"]).channel == "C_TEST"
    assert reo.CHANNEL.startswith("C")
