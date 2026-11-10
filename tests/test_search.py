# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Tests of the evaluation of Bugzilla searches by the fake Bugzilla.

The expected semantics are BMO's (Bugzilla/Search.pm), not what would seem
natural: add a test here for anything added to `tests/framework/search.py`.
"""

import datetime
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from tests.framework.bugs import normalize_bug
from tests.framework.search import (
    InvalidSearch,
    Search,
    UnsupportedSearch,
    sqlify_date,
)

NOW = datetime.datetime(2026, 11, 10, 8, 30)  # A Tuesday.


def _params(params: dict) -> dict:
    """The parameters as received by Bugzilla, encoded by requests."""
    url = requests.Request("GET", "https://bmo/rest/bug", params=params).prepare().url
    return parse_qs(urlparse(url).query, keep_blank_values=True)


def matches(params: dict, users=None, **bug) -> bool:
    bug = normalize_bug({"id": 1, **bug}, {}, "2026-11-10T08:30:00Z")
    return Search(_params(params), NOW, users).matches(bug)


def cond(field, operator, value="", negate=False):
    params = {"f1": field, "o1": operator, "v1": value}
    if negate:
        params["n1"] = 1
    return params


@pytest.mark.parametrize(
    "value, expected",
    [
        ("now", datetime.datetime(2026, 11, 10)),
        ("-2d", datetime.datetime(2026, 11, 8, 8, 30)),
        ("2d", datetime.datetime(2026, 11, 8, 8, 30)),
        ("+2d", datetime.datetime(2026, 11, 12, 8, 30)),
        ("-1ds", datetime.datetime(2026, 11, 9)),
        ("0d", datetime.datetime(2026, 11, 10)),
        ("-2w", datetime.datetime(2026, 10, 27, 8, 30)),
        # Start of the week, Perl's wday: Monday is 1, so this is Sunday.
        ("0w", datetime.datetime(2026, 11, 8)),
        ("-1m", datetime.datetime(2026, 10, 10, 8, 30)),
        ("-1ms", datetime.datetime(2026, 10, 1)),
        ("-1y", datetime.datetime(2025, 11, 10, 8, 30)),
        ("-3h", datetime.datetime(2026, 11, 10, 5, 30)),
        ("2026-10-02", datetime.datetime(2026, 10, 2)),
        ("2026-10-02T10:00:00Z", datetime.datetime(2026, 10, 2, 10)),
    ],
)
def test_sqlify_date(value, expected):
    assert sqlify_date(value, NOW) == expected


def test_top_level_params():
    assert matches({"product": ["Core", "Firefox"]}, product="Firefox")
    assert not matches({"product": "Core"}, product="Firefox")
    # REST API names.
    assert matches({"status": "NEW", "severity": "S2"}, severity="S2")
    assert not matches({"type": "task"})
    # Case insensitive, like MySQL.
    assert matches({"product": "core"})
    assert matches({"resolution": "---"})
    assert not matches({"resolution": "---"}, resolution="FIXED")
    assert matches({"resolution": ["---", "FIXED"]}, resolution="FIXED")
    assert matches({"bug_status": "__open__"}, status="REOPENED")
    assert not matches({"bug_status": "__closed__"}, status="REOPENED")
    assert matches({"bug_id": "1,2"}) and not matches({"bug_id": "2"})


def test_unsupported():
    with pytest.raises(UnsupportedSearch, match="'unknown_field'"):
        matches({"unknown_field": "x"})
    with pytest.raises(UnsupportedSearch, match="'matches'"):
        matches(cond("short_desc", "matches", "x"))
    with pytest.raises(UnsupportedSearch, match="'status'"):
        # Custom searches use the internal names (bug_status).
        matches(cond("status", "equals", "NEW"))


def test_invalid():
    with pytest.raises(InvalidSearch, match="word boundaries"):
        matches(cond("short_desc", "regexp", "[[:<:]]crash"))


def test_creation_time_and_last_change_time_are_lower_bounds():
    assert matches(
        {"creation_time": "2026-11-01"}, creation_time="2026-11-02T00:00:00Z"
    )
    assert not matches(
        {"last_change_time": "2026-11-03"}, last_change_time="2026-11-02T00:00:00Z"
    )


def test_keywords_default_to_all_words():
    assert matches({"keywords": "crash, regression"}, keywords=["regression", "crash"])
    assert not matches({"keywords": "crash, regression"}, keywords=["crash"])
    assert matches(
        {"keywords": "crash, meta", "keywords_type": "anywords"}, keywords=["crash"]
    )
    assert matches({"keywords": "meta", "keywords_type": "nowords"}, keywords=["crash"])


def test_summary_defaults_to_all_words_as_substrings():
    assert matches({"summary": "crash foo"}, summary="Crashes in Foobar")
    assert not matches({"summary": "crash baz"}, summary="Crashes in Foobar")


@pytest.mark.parametrize(
    "operator, value, expected",
    [
        ("equals", "crash in foo", True),
        ("notequals", "crash in foo", False),
        ("substring", "IN F", True),
        ("casesubstring", "IN F", False),
        ("casesubstring", "in F", True),
        ("notsubstring", "bar", True),
        ("regexp", "^crash.*o$", True),
        ("regexp", "^[[:alpha:]]+ in", True),
        ("notregexp", "foo", False),
        ("anywords", "bar crash", True),
        ("anywords", "cras", False),
        ("allwords", "crash foo", True),
        ("allwords", "crash bar", False),
        ("nowords", "bar baz", True),
        ("anywordssubstr", "cra bar", True),
        ("allwordssubstr", "cra oo", True),
        ("nowordssubstr", "cra", False),
        ("anyexact", "crash in Foo,bar", True),
        ("isempty", "", False),
        ("isnotempty", "", True),
        ("lessthan", "d", True),
        ("greaterthan", "d", False),
    ],
)
def test_string_operators(operator, value, expected):
    assert (
        matches(cond("short_desc", operator, value), summary="Crash in Foo") == expected
    )


def test_empty_values_are_ignored():
    assert matches(cond("short_desc", "equals", ""), summary="x")
    assert matches(cond("short_desc", "anywords", ", "), summary="x")


def test_negation_and_nesting():
    params = {
        "j_top": "OR",
        "f1": "bug_severity",
        "o1": "equals",
        "v1": "S1",
        "f2": "OP",
        "n2": 1,
        "f3": "priority",
        "o3": "equals",
        "v3": "P1",
        "f4": "CP",
    }
    assert matches(params, severity="S1", priority="P1")
    assert matches(params, severity="S3", priority="P3")
    assert not matches(params, severity="S3", priority="P1")


def test_numbers_and_dates():
    assert matches(cond("votes", "greaterthan", "9"), votes=10)
    assert matches(
        cond("creation_ts", "lessthan", "-1w"), creation_time="2026-11-01T00:00:00Z"
    )
    assert not matches(
        cond("creation_ts", "lessthan", "2026-11-01"),
        creation_time="2026-11-01T00:00:00Z",
    )
    assert matches(
        cond("delta_ts", "greaterthaneq", "2026-11-01"),
        last_change_time="2026-11-01T00:00:00Z",
    )
    assert matches(
        cond("days_elapsed", "greaterthan", "8"),
        last_change_time="2026-11-01T23:00:00Z",
    )
    assert not matches(
        cond("days_elapsed", "greaterthan", "9"),
        last_change_time="2026-11-01T00:00:00Z",
    )


def test_empty_custom_datetime_is_1970():
    assert matches(cond("cf_last_resolved", "lessthan", "2026-01-01"))
    assert matches(cond("cf_last_resolved", "isempty"))
    assert not matches(
        cond("cf_last_resolved", "isempty"), cf_last_resolved="2026-01-01T00:00:00Z"
    )


def test_status_flags_of_any_version():
    assert matches(cond("cf_status_firefox120", "equals", "---"))
    assert matches(
        cond("cf_status_firefox120", "anyexact", "affected,fixed"),
        cf_status_firefox120="fixed",
    )


@pytest.mark.parametrize("field", ["keywords", "dependson", "blocked", "bug_group"])
def test_multi_value_fields(field):
    bug_field = {
        "dependson": "depends_on",
        "blocked": "blocks",
        "bug_group": "groups",
    }.get(field, field)
    values = {"keywords": ["crash", "regression"], "bug_group": ["a", "b"]}.get(
        field, [10, 20]
    )
    bug = {bug_field: values}
    a, b = map(str, values)
    assert matches(cond(field, "equals", a), **bug)
    assert matches(cond(field, "anyexact", f"x,{b}"), **bug)
    assert not matches(cond(field, "allwords", f"{a} x"), **bug)
    assert matches(cond(field, "allwords", f"{a} {b}"), **bug)
    # Negative operators: none of the values matches.
    assert not matches(cond(field, "notequals", a), **bug)
    assert matches(cond(field, "notequals", "x"), **bug)
    assert not matches(cond(field, "nowords", f"x {b}"), **bug)
    assert matches(cond(field, "isnotempty"), **bug)
    assert matches(cond(field, "isempty"))


def test_flags():
    flags = [
        {"name": "needinfo", "requestee": "a@b.c"},
        {"name": "qe-verify", "status": "+"},
    ]
    attachments = [{"flags": [{"name": "approval-mozilla-beta", "status": "?"}]}]
    assert matches(cond("flagtypes.name", "substring", "needinfo?"), flags=flags)
    assert matches(cond("flagtypes.name", "equals", "qe-verify+"), flags=flags)
    assert matches(
        cond("flagtypes.name", "substring", "approval-mozilla-beta?"),
        attachments=attachments,
    )
    # Negative operators: no flag matches.
    assert not matches(cond("flagtypes.name", "notsubstring", "needinfo"), flags=flags)
    assert matches(cond("flagtypes.name", "notsubstring", "needinfo"))
    assert matches(cond("flagtypes.name", "isempty"))
    assert matches(cond("requestees.login_name", "equals", "a@b.c"), flags=flags)
    assert matches(
        cond("setters.login_name", "equals", "reporter@example.com"), flags=flags
    )


def test_comments():
    comments = ["Steps to reproduce: foo", "It's fixed"]
    assert matches(cond("longdesc", "substring", "STEPS"), comments=comments)
    # Matches if any comment doesn't contain it: use the negation instead.
    assert matches(cond("longdesc", "notsubstring", "fixed"), comments=comments)
    assert not matches(
        cond("longdesc", "substring", "fixed", negate=True), comments=comments
    )
    assert not matches({"description": "fixed"}, comments=comments)
    assert matches({"description": "steps foo"}, comments=comments)
    assert matches(
        cond("commenter", "equals", "reporter@example.com"), comments=comments
    )
    assert matches(cond("longdescs.count", "greaterthan", "1"), comments=comments)
    assert matches(cond("longdesc", "changedafter", "2026-11-09"), comments=comments)


def test_attachments():
    attachments = [
        {"file_name": "phabricator-D1-url.txt", "is_obsolete": 1},
        {"file_name": "log.txt"},
    ]
    params = cond("attachments.mimetype", "anyexact", "text/x-phabricator-request")
    assert matches(params, attachments=attachments)
    assert matches(
        cond("attachments.isobsolete", "equals", "0"), attachments=attachments
    )
    assert not matches(
        cond("attachments.mimetype", "equals", "text/html"), attachments=attachments
    )


def test_users():
    assert matches(cond("assigned_to", "equals", "nobody@mozilla.org"))
    assert matches(cond("reporter", "substring", "REPORTER"))
    assert matches({"assigned_to": "x@y.z nobody"})  # anywordssubstr
    assert matches(cond("cc", "equals", "a@b.c"), cc=["a@b.c", "d@e.f"])
    # Negative operators (starting with "no") on a user list: no user matches.
    assert not matches(cond("cc", "notequals", "a@b.c"), cc=["a@b.c", "d@e.f"])
    assert matches(cond("cc", "notequals", "x@y.z"), cc=["a@b.c", "d@e.f"])
    assert not matches(cond("cc", "nowords", "a@b.c"), cc=["a@b.c", "d@e.f"])
    assert matches({"email1": "a@b.c", "emailcc1": 1}, cc=["a@b.c"])
    assert not matches({"email1": "a@b.c", "emailassigned_to1": 1}, cc=["a@b.c"])

    users = {"reporter@example.com": {"groups": [{"name": "editbugs"}]}}
    params = cond("reporter", "equals", "%group.editbugs%")
    assert matches(params, users)
    assert not matches(params)
    assert matches(cond("reporter", "notequals", "%group.editbugs%"))


def test_history():
    history = [
        {
            "when": "2026-11-01T00:00:00Z",
            "who": "a@b.c",
            "changes": [
                {"field_name": "status", "removed": "NEW", "added": "ASSIGNED"},
                {"field_name": "priority", "removed": "--", "added": "P1"},
            ],
        },
        {
            "when": "2026-11-05T00:00:00Z",
            "who": "d@e.f",
            "changes": [
                {"field_name": "status", "removed": "ASSIGNED", "added": "NEW"}
            ],
        },
    ]
    assert matches(cond("bug_status", "changedafter", "2026-11-04"), history=history)
    assert not matches(cond("priority", "changedafter", "2026-11-04"), history=history)
    assert matches(cond("priority", "changedbefore", "-1w"), history=history)
    assert matches(cond("bug_status", "changedto", "assigned"), history=history)
    assert matches(cond("bug_status", "changedfrom", "NEW"), history=history)
    assert matches(cond("priority", "changedby", "a@b.c"), history=history)
    assert not matches(cond("priority", "changedby", "d@e.f"), history=history)
    assert matches(cond("priority", "everchanged"), history=history)
    assert not matches(cond("bug_severity", "everchanged"), history=history)
    assert matches(cond("anything", "changedby", "d@e.f"), history=history)
    assert matches(cond("creation_ts", "changedafter", "2026-11-10"))

    # `chfield` (and AND_G): the conditions must match the same change.
    chfield = {
        "chfield": "bug_status",
        "chfieldvalue": "NEW",
        "chfieldfrom": "2026-11-04",
    }
    assert matches(chfield, history=history, last_change_time="2026-11-05T00:00:00Z")
    chfield["chfieldvalue"] = "ASSIGNED"
    assert not matches(
        chfield, history=history, last_change_time="2026-11-05T00:00:00Z"
    )
