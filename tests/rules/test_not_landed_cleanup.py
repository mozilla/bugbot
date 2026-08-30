# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from bugbot import db, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.rules.not_landed import (
    NEEDINFO_TRACKING_PREFIX,
    NOT_LANDED_COMMENT_MARKER,
)
from bugbot.rules.not_landed_cleanup import NotLandedCleanup

BOT = "release-mgmt-account-bot@mozilla.tld"
REQUEST_TIME = "2026-08-14T12:10:35Z"


def _change(bugid, extra):
    return SimpleNamespace(
        bugid=bugid,
        extra=SimpleNamespace(extra=extra) if extra else None,
    )


def _flag(flag_id, setter=BOT, creation_date=REQUEST_TIME):
    return {
        "id": flag_id,
        "name": "needinfo",
        "status": "?",
        "setter": setter,
        "requestee": f"user-{flag_id}@example.com",
        "creation_date": creation_date,
    }


def _not_landed_comment(
    text="There is an r+ patch which didn't land and no activity in this bug for 1 week.",
):
    return {
        "creator": BOT,
        "creation_time": REQUEST_TIME,
        "text": text,
    }


def _bug(bugid, status="NEW", flags=None):
    return {
        "id": int(bugid),
        "summary": f"Bug {bugid}",
        "status": status,
        "comments": [_not_landed_comment()],
        "flags": flags if flags is not None else [_flag(int(bugid))],
    }


def _rule(monkeypatch):
    monkeypatch.setattr(utils, "get_login_info", lambda: {"phab_api_key": "test-key"})
    rule = NotLandedCleanup()
    rule.dryrun = True
    return rule


def _set_bugs(monkeypatch, bugs):
    monkeypatch.setattr(
        BzCleaner,
        "get_bugs",
        lambda self, date="today", bug_ids=[]: bugs,
    )


def test_query_finds_current_not_landed_needinfos(monkeypatch):
    rule = _rule(monkeypatch)

    params = rule.get_bz_params("today")

    assert params["v1"] == "needinfo?"
    assert params["v2"] == BOT
    assert params["v3"] == NOT_LANDED_COMMENT_MARKER
    assert {"flags", "status"} <= set(params["include_fields"])


def test_revision_tracking_distinguishes_legacy_and_empty_results():
    changes = [
        _change(1, "first@example.com"),
        _change(2, f"{NEEDINFO_TRACKING_PREFIX}20,21"),
        _change(2, f"{NEEDINFO_TRACKING_PREFIX}22"),
        _change(3, NEEDINFO_TRACKING_PREFIX),
    ]

    assert NotLandedCleanup.get_revision_tracking(
        changes, {"1", "2", "3"}
    ) == {
        "1": None,
        "2": {20, 21, 22},
        "3": set(),
    }


def test_not_landed_needinfos_exclude_unrelated_flags():
    owned = _flag(1)
    other_rule = _flag(2, creation_date="2026-08-15T12:10:35Z")
    human = _flag(3, setter="human@example.com")
    bug = {
        "comments": [
            _not_landed_comment(),
            {
                "creator": BOT,
                "creation_time": other_rule["creation_date"],
                "text": "A different BugBot rule created this needinfo.",
            },
        ],
        "flags": [owned, other_rule, human],
    }

    assert NotLandedCleanup.get_not_landed_needinfos(bug) == [owned]


def test_historical_not_landed_comment_is_recognized():
    owned = _flag(1)
    bug = {
        "comments": [
            _not_landed_comment(
                "There's a r+ patch which didn't land and no activity in this bug for 1 week."
            )
        ],
        "flags": [owned],
    }

    assert NotLandedCleanup.get_not_landed_needinfos(bug) == [owned]


def test_resolved_bug_clears_only_owned_flags(monkeypatch):
    rule = _rule(monkeypatch)
    owned = _flag(1)
    unrelated = _flag(2, creation_date="2026-08-15T12:10:35Z")
    bugs = {"123": _bug("123", status="RESOLVED", flags=[owned, unrelated])}
    _set_bugs(monkeypatch, bugs)
    monkeypatch.setattr(
        rule, "get_tracked_revision_ids", lambda bugids: {"123": {123}}
    )
    monkeypatch.setattr(rule, "get_landed_bug_ids", lambda revisions: set())

    assert rule.get_bugs() == bugs
    assert rule.autofix_changes == {
        "123": {"flags": [{"id": owned["id"], "status": "X"}]}
    }


def test_open_bug_with_landed_patch_is_cleared(monkeypatch):
    rule = _rule(monkeypatch)
    bugs = {"123": _bug("123")}
    _set_bugs(monkeypatch, bugs)
    monkeypatch.setattr(
        rule, "get_tracked_revision_ids", lambda bugids: {"123": {123}}
    )
    rule.phab = SimpleNamespace(
        load_revision=lambda rev_id: {"fields": {"status": {"value": "published"}}}
    )

    rule.get_bugs()

    assert rule.autofix_changes == {
        "123": {"flags": [{"id": 123, "status": "X"}]}
    }


def test_all_relevant_patches_must_land(monkeypatch):
    rule = _rule(monkeypatch)
    rule.phab = SimpleNamespace(
        load_revision=lambda rev_id: {
            "fields": {
                "status": {"value": "published" if rev_id == 123 else "accepted"},
            }
        }
    )

    assert rule.get_landed_bug_ids({"123": {123, 124}}) == set()


def test_cleanup_is_capped_to_framework_limit(monkeypatch):
    rule = _rule(monkeypatch)
    bugs = {
        str(bugid): _bug(str(bugid), status="RESOLVED")
        for bugid in range(1, 52)
    }
    _set_bugs(monkeypatch, bugs)
    monkeypatch.setattr(
        rule,
        "get_tracked_revision_ids",
        lambda bugids: {bugid: {int(bugid)} for bugid in bugids},
    )
    monkeypatch.setattr(rule, "get_landed_bug_ids", lambda revisions: set())

    rule.get_bugs()

    assert len(rule.autofix_changes) == rule.normal_changes_max
    assert "50" in rule.autofix_changes
    assert "51" not in rule.autofix_changes


def test_legacy_tracking_ignores_patches_attached_after_needinfo(monkeypatch):
    rule = _rule(monkeypatch)
    before_needinfo = {
        "creation_time": "2026-08-13T12:10:35Z",
        "data": base64.b64encode(
            b"https://phabricator.services.mozilla.com/D123"
        ).decode(),
    }
    after_needinfo = {
        "creation_time": "2026-08-15T12:10:35Z",
        "data": base64.b64encode(
            b"https://phabricator.services.mozilla.com/D124"
        ).decode(),
    }
    monkeypatch.setattr(
        rule,
        "get_phab_attachments",
        lambda bugids: {"123": [before_needinfo, after_needinfo]},
    )

    assert rule.get_legacy_revision_ids({"123": [_flag(1)]}) == {"123": {123}}


def test_empty_legacy_result_is_recorded(monkeypatch):
    rule = _rule(monkeypatch)
    recorded = []
    rule.dryrun = False
    rule.test_mode = False
    monkeypatch.setattr(
        db.BugChange,
        "add",
        lambda name, bugid, extra: recorded.append((name, bugid, extra)),
    )

    rule.record_revision_ids({"123": set()})

    assert recorded == [("not_landed_cleanup", "123", NEEDINFO_TRACKING_PREFIX)]


def test_test_mode_does_not_record_legacy_results(monkeypatch):
    rule = _rule(monkeypatch)
    rule.dryrun = False
    rule.test_mode = True
    monkeypatch.setattr(
        db.BugChange,
        "add",
        lambda name, bugid, extra: raise_error(),
    )

    rule.record_revision_ids({"123": {123}})


def test_abort_template_escapes_summary():
    env = Environment(loader=FileSystemLoader("templates"))
    rendered = env.get_template("not_landed_cleanup.html").render(
        data=[("123", "<private>")],
        table_attrs="",
    )

    assert "&lt;private&gt;" in rendered
    assert "<private>" not in rendered


def raise_error():
    raise AssertionError("DB write should not happen")
