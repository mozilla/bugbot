# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest.mock import Mock

import pytest
from jinja2 import Environment, FileSystemLoader

from bugbot import db
from bugbot.bzcleaner import BzCleaner
from bugbot.rules.not_landed import NOT_LANDED_COMMENT_MARKER
from bugbot.rules.not_landed_cleanup import NotLandedCleanup

BOT = "release-mgmt-account-bot@mozilla.tld"
REQUEST_TIME = "2026-08-14T12:10:35Z"


def _flag(flag_id, **overrides):
    return {
        "id": flag_id,
        "name": "needinfo",
        "status": "?",
        "setter": BOT,
        "requestee": f"user-{flag_id}@example.com",
        "creation_date": REQUEST_TIME,
        **overrides,
    }


def _comment(**overrides):
    return {
        "creator": BOT,
        "creation_time": REQUEST_TIME,
        "text": "There is an r+ patch which didn't land and no activity in this bug for 1 week.",
        **overrides,
    }


def _bug(bugid="123", **overrides):
    return {
        "id": int(bugid),
        "summary": f"Bug {bugid}",
        "status": "RESOLVED",
        "resolution": "FIXED",
        "comments": [_comment()],
        "flags": [_flag(int(bugid))],
        **overrides,
    }


def _set_bugs(monkeypatch, bugs):
    monkeypatch.setattr(
        BzCleaner,
        "get_bugs",
        lambda self, date="today", bug_ids=[], chunk_size=None: bugs,
    )


def test_query_finds_closed_fixed_bugs():
    rule = NotLandedCleanup()
    params = rule.get_bz_params("today")

    assert set(params["status"]) == {"RESOLVED", "VERIFIED", "CLOSED"}
    assert params["resolution"] == "FIXED"
    assert params["v1"] == "needinfo?"
    assert params["v2"] == BOT
    assert params["v3"] == NOT_LANDED_COMMENT_MARKER
    assert {"flags", "status", "resolution"} <= set(params["include_fields"])
    assert rule.filter_no_nag_keyword() is False
    assert rule.has_last_comment_time() is True


@pytest.mark.parametrize("status", ["RESOLVED", "VERIFIED", "CLOSED"])
def test_fixed_bug_clears_only_owned_flags(monkeypatch, status):
    rule = NotLandedCleanup()
    owned = [_flag(1), _flag(2)]
    other_time = "2026-08-15T12:10:35Z"
    unrelated = [
        _flag(3, setter="human@example.com"),
        _flag(4, creation_date=other_time),
        _flag(5, name="review"),
        _flag(6, status="+"),
    ]
    bug = _bug(
        status=status,
        flags=owned + unrelated,
        comments=[
            _comment(),
            _comment(
                creation_time=other_time,
                text="A different BugBot rule created this needinfo.",
            ),
        ],
    )
    _set_bugs(monkeypatch, {"123": bug})

    assert rule.get_bugs() == {"123": bug}
    assert rule.autofix_changes == {
        "123": {"flags": [{"id": 1, "status": "X"}, {"id": 2, "status": "X"}]}
    }


@pytest.mark.parametrize("status", ["NEW", "ASSIGNED", "REOPENED", "UNCONFIRMED"])
def test_open_bug_is_not_cleared(monkeypatch, status):
    rule = NotLandedCleanup()
    _set_bugs(monkeypatch, {"123": _bug(status=status, resolution="---")})

    assert rule.get_bugs() == {}
    assert rule.autofix_changes == {}


@pytest.mark.parametrize(
    "resolution", ["DUPLICATE", "WONTFIX", "INVALID", "WORKSFORME", "INCOMPLETE", "---"]
)
def test_non_fixed_resolution_is_not_cleared(monkeypatch, resolution):
    rule = NotLandedCleanup()
    _set_bugs(monkeypatch, {"123": _bug(resolution=resolution)})

    assert rule.get_bugs() == {}
    assert rule.autofix_changes == {}


@pytest.mark.parametrize(
    "comments",
    [
        [],
        [_comment(creator="human@example.com")],
        [_comment(text="A different BugBot rule created this needinfo.")],
        [_comment(creation_time="2026-08-15T12:10:35Z")],
    ],
)
def test_unattributable_flags_are_not_cleared(monkeypatch, comments):
    rule = NotLandedCleanup()
    _set_bugs(monkeypatch, {"123": _bug(comments=comments)})

    assert rule.get_bugs() == {}
    assert rule.autofix_changes == {}


def test_historical_comment_is_recognized(monkeypatch):
    rule = NotLandedCleanup()
    bug = _bug(
        comments=[
            _comment(
                text="There's a r+ patch which didn't land and no activity in this bug for 1 week."
            )
        ]
    )
    _set_bugs(monkeypatch, {"123": bug})

    assert rule.get_bugs() == {"123": bug}
    assert rule.autofix_changes == {"123": {"flags": [{"id": 123, "status": "X"}]}}


def test_cleanup_cap_leaves_overflow_for_later_runs(monkeypatch):
    rule = NotLandedCleanup()
    bugs = {str(bugid): _bug(str(bugid)) for bugid in range(51, 0, -1)}
    _set_bugs(monkeypatch, bugs)

    assert len(rule.get_bugs()) == rule.normal_changes_max
    assert set(rule.autofix_changes) == {str(bugid) for bugid in range(1, 51)}
    for bugid in range(1, 51):
        bugs[str(bugid)]["flags"] = []

    assert rule.get_bugs() == {"51": bugs["51"]}
    bugs["51"]["flags"] = []
    assert rule.get_bugs() == {}
    assert rule.autofix_changes == {}


def test_inaccessible_bug_is_retried_when_available(monkeypatch):
    rule = NotLandedCleanup()
    _set_bugs(monkeypatch, {})
    assert rule.get_bugs() == {}
    _set_bugs(monkeypatch, {"123": _bug()})

    assert set(rule.get_bugs()) == {"123"}


@pytest.mark.parametrize("dryrun,test_mode", [(True, False), (False, True)])
def test_non_writing_modes_do_not_update_bugzilla_or_db(monkeypatch, dryrun, test_mode):
    rule = NotLandedCleanup()
    rule.dryrun = dryrun
    rule.test_mode = test_mode
    rule.is_limited = True
    _set_bugs(monkeypatch, {"123": _bug()})
    put = Mock()
    add = Mock()
    monkeypatch.setattr("bugbot.bzcleaner.Bugzilla.put", put)
    monkeypatch.setattr(db.BugChange, "add", add)

    rule.autofix(rule.get_bugs())

    put.assert_not_called()
    add.assert_not_called()


def test_template_escapes_summary():
    env = Environment(loader=FileSystemLoader("templates"))
    rendered = env.get_template("not_landed_cleanup.html").render(
        data=[("123", "<private>")], table_attrs=""
    )

    assert "&lt;private&gt;" in rendered
    assert "<private>" not in rendered
