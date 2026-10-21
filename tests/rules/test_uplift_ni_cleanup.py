# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from bugbot.bzcleaner import BzCleaner
from bugbot.rules.uplift_beta import COMMENT_MARKER, LEGACY_COMMENT_MARKER
from bugbot.rules.uplift_ni_cleanup import UpliftNiCleanup

BOT = "release-mgmt-account-bot@mozilla.tld"
TODAY = "2026-10-16"
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
        "text": f":dev, {COMMENT_MARKER} beta:",
        **overrides,
    }


def _bug(**overrides):
    return {
        "id": 123,
        "summary": "Bug 123",
        "resolution": "FIXED",
        "cf_last_resolved": "2026-08-10T00:00:00Z",
        "cf_status_firefox140": "fixed",
        "cf_status_firefox139": "wontfix",
        "cf_status_firefox_esr128": "unaffected",
        "comments": [_comment()],
        "flags": [_flag(1)],
        **overrides,
    }


def _cleared(monkeypatch, bug):
    monkeypatch.setattr(
        BzCleaner,
        "get_bugs",
        lambda self, date="today", bug_ids=[], chunk_size=None: {"123": bug},
    )
    rule = UpliftNiCleanup()
    rule.get_bugs(TODAY)
    change = rule.autofix_changes.get("123")
    return [f["id"] for f in change["flags"]] if change else []


@pytest.mark.parametrize("marker", [COMMENT_MARKER, LEGACY_COMMENT_MARKER])
def test_clears_only_uplift_needinfos(monkeypatch, marker):
    other_time = "2026-08-15T00:00:00Z"
    bug = _bug(
        comments=[
            _comment(text=f"blah {marker} blah"),
            _comment(creation_time=other_time, text="Another rule."),
        ],
        flags=[
            _flag(1),
            _flag(2, creation_date=other_time),
            _flag(3, setter="human@example.com"),
        ],
    )

    assert _cleared(monkeypatch, bug) == [1]


@pytest.mark.parametrize("field", ["cf_status_firefox139", "cf_status_firefox_esr128"])
@pytest.mark.parametrize("value", ["affected", "fix-optional"])
def test_affected_version_keeps_needinfo(monkeypatch, field, value):
    assert _cleared(monkeypatch, _bug(**{field: value})) == []


def test_open_bug_keeps_needinfo(monkeypatch):
    assert _cleared(monkeypatch, _bug(resolution="", cf_last_resolved=None)) == []


def test_comment_by_human_is_ignored(monkeypatch):
    bug = _bug(comments=[_comment(creator="human@example.com")])
    assert _cleared(monkeypatch, bug) == []


def _approval(name="approval-mozilla-beta", status="?", **overrides):
    return {
        "flags": [
            {
                "name": name,
                "status": status,
                "creation_date": "2026-08-15T00:00:00Z",
                **overrides,
            }
        ]
    }


@pytest.mark.parametrize("name", ["approval-mozilla-beta", "approval-mozilla-esr140"])
@pytest.mark.parametrize("status", ["?", "+", "-"])
def test_uplift_request_clears_needinfo_on_open_bug(monkeypatch, name, status):
    bug = _bug(
        resolution="",
        cf_last_resolved=None,
        cf_status_firefox139="affected",
        attachments=[_approval(name, status)],
    )
    assert _cleared(monkeypatch, bug) == [1]


def test_uplift_request_clears_needinfo_on_affected_closed_bug(monkeypatch):
    bug = _bug(cf_status_firefox139="affected", attachments=[_approval()])
    assert _cleared(monkeypatch, bug) == [1]


def test_uplift_request_before_needinfo_is_ignored(monkeypatch):
    bug = _bug(
        resolution="",
        cf_last_resolved=None,
        attachments=[_approval(creation_date="2026-08-01T00:00:00Z")],
    )
    assert _cleared(monkeypatch, bug) == []


def test_other_attachment_flags_are_ignored(monkeypatch):
    bug = _bug(
        resolution="",
        cf_last_resolved=None,
        attachments=[_approval(name="review")],
    )
    assert _cleared(monkeypatch, bug) == []


def test_uplift_request_keeps_human_needinfo(monkeypatch):
    bug = _bug(
        resolution="",
        cf_last_resolved=None,
        flags=[_flag(1), _flag(2, setter="human@example.com")],
        attachments=[_approval()],
    )
    assert _cleared(monkeypatch, bug) == [1]
