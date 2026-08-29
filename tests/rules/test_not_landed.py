# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
from types import SimpleNamespace

from bugbot import utils
from bugbot.rules.not_landed import (
    NEEDINFO_CLEANUP_MARKER,
    NEEDINFO_TRACKING_PREFIX,
    NotLanded,
)

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


def _not_landed_comment():
    return {
        "creator": BOT,
        "creation_time": REQUEST_TIME,
        "text": "There is an r+ patch which didn't land and no activity in this bug for 1 week.",
    }


def _rule(monkeypatch):
    monkeypatch.setattr(utils, "get_login_info", lambda: {"phab_api_key": "test-key"})
    rule = NotLanded()
    rule.dryrun = True
    return rule


def test_pending_needinfos_follow_cleanup_markers():
    changes = [
        _change(1, "first@example.com"),
        _change(2, f"{NEEDINFO_TRACKING_PREFIX}20,21"),
        _change(1, NEEDINFO_CLEANUP_MARKER),
        _change(1, f"{NEEDINFO_TRACKING_PREFIX}10"),
        _change(2, NEEDINFO_CLEANUP_MARKER),
        _change(3, ""),
    ]

    assert NotLanded.get_pending_needinfos(changes) == {"1": {10}}


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

    assert NotLanded.get_not_landed_needinfos(bug) == [owned]


def test_schedule_cleanup_for_resolved_bug_clears_only_owned_flags(monkeypatch):
    rule = _rule(monkeypatch)
    owned = _flag(1)
    unrelated = _flag(2, creation_date="2026-08-15T12:10:35Z")
    monkeypatch.setattr(
        rule,
        "get_needinfo_cleanup_bugs",
        lambda bugids: {
            "123": {
                "status": "RESOLVED",
                "comments": [_not_landed_comment()],
                "flags": [owned, unrelated],
            }
        },
    )
    monkeypatch.setattr(rule, "get_pending_needinfo_tracking", lambda: {"123": {123}})
    monkeypatch.setattr(rule, "get_landed_bug_ids", lambda bugs: set())

    rule.schedule_needinfo_cleanup()

    assert rule.autofix_changes == {
        "123": {"flags": [{"id": owned["id"], "status": "X"}]}
    }
    assert rule.get_db_extra()["123"] == NEEDINFO_CLEANUP_MARKER


def test_new_needinfo_tracks_exact_revision_ids(monkeypatch):
    rule = _rule(monkeypatch)
    rule.needinfo_revision_ids = {"123": {124, 123}}

    assert rule.get_db_extra()["123"] == f"{NEEDINFO_TRACKING_PREFIX}123,124"


def test_unlanded_attachment_records_revision_id(monkeypatch):
    rule = _rule(monkeypatch)
    monkeypatch.setattr(rule, "check_phab", lambda attachment, reviewers: True)
    result = {"reviewers_phid": set()}
    attachment = {
        "content_type": "text/x-phabricator-request",
        "creator": "author@example.com",
        "data": base64.b64encode(
            b"https://phabricator.services.mozilla.com/D123"
        ).decode(),
    }

    rule.handle_attachment(attachment, result)

    assert result["revision_ids"] == {123}


def test_landed_patch_after_needinfo_is_cleaned_up(monkeypatch):
    rule = _rule(monkeypatch)
    rule.phab = SimpleNamespace(
        load_revision=lambda rev_id: {
            "fields": {
                "status": {"value": "published"},
            }
        }
    )

    assert rule.get_landed_bug_ids({"123": {123, 124}}) == {"123"}


def test_schedule_cleanup_for_landed_patch(monkeypatch):
    rule = _rule(monkeypatch)
    owned = _flag(1)
    monkeypatch.setattr(rule, "get_pending_needinfo_tracking", lambda: {"123": {123}})
    monkeypatch.setattr(
        rule,
        "get_needinfo_cleanup_bugs",
        lambda bugids: {
            "123": {
                "status": "NEW",
                "comments": [_not_landed_comment()],
                "flags": [owned],
            }
        },
    )
    rule.phab = SimpleNamespace(
        load_revision=lambda rev_id: {"fields": {"status": {"value": "published"}}}
    )

    rule.schedule_needinfo_cleanup()

    assert rule.autofix_changes == {
        "123": {"flags": [{"id": owned["id"], "status": "X"}]}
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


def test_manually_cleared_needinfo_retires_tracking(monkeypatch):
    rule = _rule(monkeypatch)
    retired = set()
    monkeypatch.setattr(rule, "get_pending_needinfo_tracking", lambda: {"123": {123}})
    monkeypatch.setattr(
        rule,
        "get_needinfo_cleanup_bugs",
        lambda bugids: {
            "123": {
                "status": "NEW",
                "comments": [_not_landed_comment()],
                "flags": [],
            }
        },
    )
    monkeypatch.setattr(
        rule, "mark_needinfo_tracking_complete", lambda bugids: retired.update(bugids)
    )
    monkeypatch.setattr(rule, "get_landed_bug_ids", lambda bugs: set())

    rule.schedule_needinfo_cleanup()

    assert retired == {"123"}


def test_unavailable_bug_retires_tracking(monkeypatch):
    rule = _rule(monkeypatch)
    retired = set()
    monkeypatch.setattr(rule, "get_pending_needinfo_tracking", lambda: {"123": {123}})
    monkeypatch.setattr(rule, "get_needinfo_cleanup_bugs", lambda bugids: {})
    monkeypatch.setattr(
        rule, "mark_needinfo_tracking_complete", lambda bugids: retired.update(bugids)
    )
    monkeypatch.setattr(rule, "get_landed_bug_ids", lambda bugs: set())

    rule.schedule_needinfo_cleanup()

    assert retired == {"123"}
