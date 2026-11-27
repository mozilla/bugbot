# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Tests of the scenario framework itself (see `tests/framework`)."""

import pytest
import requests

from tests.framework import bmo as bmo_module
from tests.framework.bugs import link_bugs, make_user, normalize_bug
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


def _bugs(*bugs):
    bugs = {b["id"]: normalize_bug(b, {}, NOW) for b in bugs}
    link_bugs(bugs)
    return bugs


def test_relations_are_mirrored():
    bugs = _bugs(
        {"id": 1, "regressed_by": [2], "depends_on": [3], "dupe_of": 4},
        {"id": 2},
        {"id": 3},
        {"id": 4, "duplicates": [5]},
    )
    assert bugs[2]["regressions"] == [1]
    assert bugs[3]["blocks"] == [1]
    assert bugs[4]["duplicates"] == [1, 5]


def test_load_bugs(bmo):
    """The bugs read from BMO are the bugs of the scenario."""
    bugs = _bugs(
        {
            "id": 1,
            "summary": "Crash in Foo",
            "status": "RESOLVED",
            "resolution": "FIXED",
            "cf_last_resolved": "2026-11-01T10:00:00Z",
            "creation_time": "2026-10-01T10:00:00Z",
            "assigned_to": "dev@mozilla.com",
            "keywords": ["regression", "new-keyword"],
            "regressed_by": [2],
            "cc": ["cc@example.com"],
            "cf_status_firefox150": "fixed",
            "cf_has_str": "yes",
            "flags": [{"name": "needinfo", "requestee": "ni@example.com"}],
            "comments": [
                "Steps to reproduce",
                {"text": "Fixed", "author": "dev@mozilla.com"},
            ],
            "history": [
                {
                    "when": "2026-11-01T10:00:00Z",
                    "who": "dev@mozilla.com",
                    "changes": [
                        {"field_name": "status", "removed": "NEW", "added": "RESOLVED"}
                    ],
                }
            ],
            "attachments": [{"file_name": "phabricator-D1-url.txt"}],
        },
        {"id": 2, "product": "Firefox", "component": "New Tab Page"},
    )
    users = {"dev@mozilla.com": make_user("dev@mozilla.com", {"real_name": "Dev"}, NOW)}
    bmo.load(bugs, users, NOW)

    bug = requests.get(
        f"{bmo_module.URL}/rest/bug/1",
        params={"include_fields": "_all"},
        headers={"X-Bugzilla-API-Key": bmo.api_key},
    ).json()["bugs"][0]
    assert bug["summary"] == "Crash in Foo"
    assert (bug["status"], bug["resolution"]) == ("RESOLVED", "FIXED")
    assert bug["cf_last_resolved"] == "2026-11-01T10:00:00Z"
    assert bug["creation_time"] == "2026-10-01T10:00:00Z"
    assert bug["assigned_to_detail"]["real_name"] == "Dev"
    assert sorted(bug["keywords"]) == ["new-keyword", "regression"]
    assert bug["regressed_by"] == [2]
    assert bug["cc"] == ["cc@example.com"]
    assert bug["cf_status_firefox150"] == "fixed"
    assert bug["cf_has_str"] == "yes"
    assert [(f["name"], f["status"], f["requestee"]) for f in bug["flags"]] == [
        ("needinfo", "?", "ni@example.com")
    ]
    assert [c["text"] for c in bug["comments"]] == ["Steps to reproduce", "Fixed"]
    assert bug["history"] == [
        {
            "when": "2026-11-01T10:00:00Z",
            "who": "dev@mozilla.com",
            "changes": [
                {"field_name": "status", "removed": "NEW", "added": "RESOLVED"}
            ],
        }
    ]
    assert bug["attachments"][0]["content_type"] == "text/x-phabricator-request"


def test_clock(bmo):
    """BMO's relative dates are relative to the time of the scenario."""
    bugs = _bugs(
        {"id": 1, "last_change_time": "2026-11-08T08:00:00Z"},
        {"id": 2, "last_change_time": "2026-11-01T08:00:00Z"},
    )
    bmo.load(bugs, {}, NOW)
    local = bmo_module.LocalBugzilla.__new__(bmo_module.LocalBugzilla)
    local.database = bmo
    local._session = requests.Session()
    assert local.search({"f1": ["days_elapsed"], "o1": ["lessthan"], "v1": ["5"]}) == {
        1
    }
    assert local.search({"f1": ["delta_ts"], "o1": ["lessthan"], "v1": ["-1w"]}) == {2}


def test_undefined_bug(bmo):
    with pytest.raises(AssertionError, match=r"fetched bugs \[2\]"):
        assert_scenario(
            {
                "rule": "closed_bug_ni_cleanup",
                "now": "2026-10-16",
                "bugs": [
                    {
                        "id": 1,
                        "resolution": "DUPLICATE",
                        "dupe_of": 2,
                        "flags": [{"name": "needinfo", "requestee": "a@example.com"}],
                    }
                ],
            }
        )


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


def test_inline_scenario(bmo):
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


def test_inline_scenario_failure(bmo):
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
