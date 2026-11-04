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


def _cleared(monkeypatch, bug, versions={"release": 138, "beta": 139, "esr": 128}):
    def init_versions(self):
        self.versions = versions
        return bool(versions)

    monkeypatch.setattr(BzCleaner, "init_versions", init_versions)
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
        "name": name,
        "status": status,
        "creation_date": "2026-08-15T00:00:00Z",
        **overrides,
    }


def _open_bug(**overrides):
    return _bug(resolution="", cf_last_resolved=None, **overrides)


@pytest.mark.parametrize("status", ["?", "+", "-"])
def test_beta_uplift_request_clears_needinfo(monkeypatch, status):
    bug = _open_bug(
        cf_status_firefox139="affected",
        attachments=[{"flags": [_approval(status=status)]}],
    )
    assert _cleared(monkeypatch, bug) == [1]


def test_esr_uplift_request_clears_needinfo(monkeypatch):
    bug = _open_bug(
        cf_status_firefox_esr128="affected",
        attachments=[{"flags": [_approval("approval-mozilla-esr128")]}],
    )
    assert _cleared(monkeypatch, bug) == [1]


def test_uplift_request_clears_needinfo_on_affected_closed_bug(monkeypatch):
    bug = _bug(
        cf_status_firefox139="affected",
        attachments=[{"flags": [_approval()]}],
    )
    assert _cleared(monkeypatch, bug) == [1]


@pytest.mark.parametrize(
    "approval", ["approval-mozilla-beta", "approval-mozilla-esr128"]
)
def test_partial_uplift_requests_keep_needinfo(monkeypatch, approval):
    bug = _open_bug(
        cf_status_firefox139="affected",
        cf_status_firefox_esr128="affected",
        attachments=[{"flags": [_approval(approval)]}],
    )
    assert _cleared(monkeypatch, bug) == []


def test_each_affected_esr_needs_an_uplift_request(monkeypatch):
    bug = _open_bug(
        cf_status_firefox_esr115="affected",
        cf_status_firefox_esr128="affected",
        attachments=[{"flags": [_approval("approval-mozilla-esr128")]}],
    )
    assert _cleared(monkeypatch, bug) == []

    bug["attachments"].append({"flags": [_approval("approval-mozilla-esr115")]})
    assert _cleared(monkeypatch, bug) == [1]


def test_uplift_requests_spread_over_attachments(monkeypatch):
    bug = _open_bug(
        cf_status_firefox139="affected",
        cf_status_firefox_esr128="affected",
        attachments=[
            {"flags": [_approval()]},
            {"flags": [_approval("approval-mozilla-esr128")]},
        ],
    )
    assert _cleared(monkeypatch, bug) == [1]


def test_wontfix_channel_needs_no_uplift_request(monkeypatch):
    bug = _open_bug(
        cf_status_firefox139="wontfix",
        cf_status_firefox_esr128="affected",
        attachments=[{"flags": [_approval("approval-mozilla-esr128")]}],
    )
    assert _cleared(monkeypatch, bug) == [1]


def test_older_release_status_needs_no_uplift_request(monkeypatch):
    bug = _open_bug(
        cf_status_firefox138="affected",
        cf_status_firefox139="affected",
        attachments=[{"flags": [_approval()]}],
    )
    assert _cleared(monkeypatch, bug) == [1]


def test_uplift_request_before_needinfo_is_ignored(monkeypatch):
    bug = _open_bug(
        cf_status_firefox139="affected",
        attachments=[{"flags": [_approval(creation_date="2026-08-01T00:00:00Z")]}],
    )
    assert _cleared(monkeypatch, bug) == []


def test_other_attachment_flags_are_ignored(monkeypatch):
    bug = _open_bug(attachments=[{"flags": [_approval(name="review")]}])
    assert _cleared(monkeypatch, bug) == []


def test_uplift_request_keeps_human_needinfo(monkeypatch):
    bug = _open_bug(
        cf_status_firefox139="affected",
        flags=[_flag(1), _flag(2, setter="human@example.com")],
        attachments=[{"flags": [_approval()]}],
    )
    assert _cleared(monkeypatch, bug) == [1]


def test_no_versions_only_clears_closed_bugs(monkeypatch):
    attachments = [{"flags": [_approval()]}]
    open_bug = _open_bug(cf_status_firefox139="affected", attachments=attachments)
    assert _cleared(monkeypatch, open_bug, versions={}) == []
    assert _cleared(monkeypatch, _bug(attachments=attachments), versions={}) == [1]
