# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime

from bugbot import utils
from bugbot.rules import reo_regression_slack as summary
from bugbot.rules.reo_regression_slack import ReoRegressionSlack


def test_the_rule_is_named_after_its_module():
    # Which is what `logger_extra["bugbot_rule"]` is tagged with, so a failure in
    # this message is told apart from one in the daily message.
    assert ReoRegressionSlack().name() == "reo_regression_slack"


def test_the_summary_runs_on_monday_and_thursday_only():
    rule = ReoRegressionSlack()
    monday = datetime.datetime(2026, 8, 31)
    week = [monday + datetime.timedelta(days=day) for day in range(7)]

    assert [day for day in week if rule.must_run(day)] == [
        monday,
        datetime.datetime(2026, 9, 3),  # Thursday
    ]


def test_the_cadence_comes_from_the_rule_config():
    # `BzCleaner.must_run` reads it, so the days are configuration rather than an
    # override here. Twice a week rather than daily: the counts move slowly, and a
    # summary that arrives every morning stops being read.
    assert utils.get_config("reo_regression_slack", "must_run") == ["Mon", "Thu"]


def test_a_run_can_be_pointed_at_another_day():
    # `BzCleaner`'s own --date, which is how the Mon/Thu gate is exercised without
    # waiting for a Monday.
    rule = ReoRegressionSlack()
    args = rule.get_args_parser().parse_args(["-D", "2026-09-01"])

    assert not rule.must_run(datetime.datetime(2026, 9, 1))  # Tuesday
    assert args.date == "2026-09-01"


def test_regression_group_notes_restricted_bugs_on_the_top_line_only(monkeypatch):
    bugs = [
        {"id": 1, "severity": "S2", "groups": ["core-security-release"]},
        {"id": 2, "severity": "--", "groups": []},
    ]
    rule = ReoRegressionSlack()
    monkeypatch.setattr(rule, "fetch_bugs", lambda query, fields=None: bugs)
    monkeypatch.setattr(summary, "team_of", lambda bug: "Team A")

    bullet, teams, severities = rule.regression_group(
        150, False, "New", by_team=True
    ).split("\n")

    assert bullet.endswith("|2 New Regressions> (1 restricted)")
    assert "restricted" not in teams
    assert "restricted" not in severities
    assert "1 S2+" in severities
    assert "1 missing severity" in severities


def test_the_channel_is_a_constant_the_flag_can_override():
    rule = ReoRegressionSlack()
    parser = rule.get_args_parser()

    # No flag means the module constant, which is what the cron posts to.
    rule.parse_custom_arguments(parser.parse_args([]))
    assert rule.channel == summary.CHANNEL
    assert summary.CHANNEL.startswith("C")

    rule.parse_custom_arguments(parser.parse_args(["--channel", "C_TEST"]))
    assert rule.channel == "C_TEST"
