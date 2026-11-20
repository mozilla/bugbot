# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Tests of the scenario framework itself (see `tests/framework`)."""

import pytest
import responses
from libmozdata.bugzilla import Bugzilla

from tests.framework.bugs import link_bugs, normalize_bug
from tests.framework.fake_bugzilla import FakeBugzilla
from tests.framework.scenario import (
    Anything,
    Contains,
    Result,
    assert_scenario,
    check,
    discover_scenarios,
    load_scenario,
)

NOW = "2026-11-10T08:00:00Z"


def _fake(*bugs):
    bugs = {b["id"]: normalize_bug(b, {}, NOW) for b in bugs}
    link_bugs(bugs)
    return FakeBugzilla(bugs, {}, NOW)


def _get(fake, ids=None, **params):
    data = {}

    def handler(bug, data):
        data[bug["id"]] = bug

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        fake.register(rsps)
        Bugzilla(
            ids if ids is not None else params,
            include_fields=params.pop("include_fields", "_default"),
            bughandler=handler,
            bugdata=data,
        ).wait()
    return data


def test_relations_are_mirrored():
    fake = _fake(
        {"id": 1, "regressed_by": [2], "depends_on": [3], "dupe_of": 4},
        {"id": 2},
        {"id": 3},
        {"id": 4, "duplicates": [5]},
    )
    assert fake.bugs[2]["regressions"] == [1]
    assert fake.bugs[3]["blocks"] == [1]
    assert fake.bugs[4]["duplicates"] == [1, 5]


def test_include_fields():
    fake = _fake(
        {
            "id": 1,
            "assigned_to": "dev@example.com",
            "attachments": [{"file_name": "a.txt", "is_obsolete": 1}],
        }
    )
    bug = _get(
        fake,
        [1],
        include_fields=[
            "assigned_to",
            "attachments.is_obsolete",
            "cf_status_firefox150",
            "unknown",
        ],
    )[1]
    assert bug == {
        "id": 1,
        "assigned_to": "dev@example.com",
        "assigned_to_detail": {
            "id": bug["assigned_to_detail"]["id"],
            "name": "dev@example.com",
            "email": "dev@example.com",
            "real_name": "dev [:dev]",
            "nick": "dev",
            "active": True,
        },
        "attachments": [{"is_obsolete": 1}],
        "cf_status_firefox150": "---",
    }


def test_search():
    fake = _fake({"id": 1}, {"id": 2, "status": "ASSIGNED"}, {"id": 3})
    search = {"f1": "bug_status", "o1": "equals", "v1": "NEW"}

    assert set(_get(fake, **search)) == {1, 3}
    assert set(_get(fake, **search, bug_id="2,3")) == {3}
    assert set(_get(fake, bug_id="2,3")) == {2, 3}
    assert set(_get(fake, [2])) == {2}
    assert [s["ids"] for s in fake.searches] == [[1, 3], [3], [2, 3]]


def test_unknown_bug():
    fake = _fake({"id": 1})
    _get(fake, [2])
    assert "bug 2" in fake.errors[0]


def _result(**kwargs):
    defaults = dict(
        ran=True,
        email={},
        changes={},
        silent=[],
        nags={},
        searches=[],
        created=[],
        email_body="",
    )
    return Result(**{**defaults, **kwargs})


def test_check():
    result = _result(
        email={"1": {"id": "1", "summary": "Crash"}},
        changes={"1": {"comment": {"body": "Hello world"}, "status": "NEW"}},
    )
    assert check(result, {"email": [1], "changes": {1: {"status": "NEW"}}}) == []
    assert check(result, {"email": {1: {"summary": "Crash"}}}) == []
    assert (
        check(result, {"changes": {1: {"comment": {"body": Contains("world")}}}}) == []
    )
    assert check(result, {"changes": {1: {"status": Anything(), "flags": None}}}) == []

    assert check(result, {"email": [2]}) == ["email: expected bugs ['2'], got ['1']"]
    assert check(result, {"changes": {}}) == ["changes: expected bugs [], got ['1']"]
    assert check(result, {"changes": {1: {"status": None}}}) == [
        "changes[1].status: expected no value, got 'NEW'"
    ]
    assert check(result, {"ran": False}) == ["ran: expected False, got True"]


def test_inline_scenario():
    assert_scenario(
        {
            "rule": "closed_bug_ni_cleanup",
            "now": "2026-10-16",
            "bugs": [
                {
                    "id": 1,
                    "resolution": "WONTFIX",
                    "cf_last_resolved": "2026-09-01T00:00:00Z",
                    "flags": [
                        {
                            "name": "needinfo",
                            "requestee": "a@example.com",
                            "creation_date": "2026-09-01T00:00:00Z",
                        }
                    ],
                }
            ],
            "expect": {"changes": {1: {"flags": [{"id": 100, "status": "X"}]}}},
        }
    )


def test_inline_scenario_failure():
    with pytest.raises(AssertionError, match="expected bugs"):
        assert_scenario(
            {
                "rule": "closed_bug_ni_cleanup",
                "bugs": [{"id": 1}],
                "expect": {"changes": [1]},
            }
        )


@pytest.mark.parametrize("path", discover_scenarios())
def test_scenario_files_are_valid(path):
    scenario = load_scenario(path)
    assert scenario.expect, f"{path} has no expectations"
