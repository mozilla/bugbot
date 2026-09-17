# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import date

import pytest

from bugbot.rules import perfalert_backout_warning
from bugbot.rules.perfalert_backout_warning import PerfAlertBackoutWarning
from bugbot.user_activity import UserStatus

AUTHOR = "author@mozilla.com"
SHERIFF = "sheriff@mozilla.com"
BOT = "release-mgmt-account-bot@mozilla.tld"


def needinfo_flag(setter, requestee, creation_date):
    return {
        "name": "needinfo",
        "status": "?",
        "setter": setter,
        "requestee": requestee,
        "creation_date": creation_date,
        "modification_date": creation_date,
    }


def test_get_needinfo_date_returns_oldest_sheriff_needinfo():
    flags = [
        needinfo_flag(SHERIFF, AUTHOR, "2026-08-26T10:00:00Z"),
        needinfo_flag("other@mozilla.com", AUTHOR, "2026-08-24T10:00:00Z"),
    ]

    assert PerfAlertBackoutWarning.get_needinfo_date(flags, AUTHOR) == date(2026, 8, 24)


def test_get_needinfo_date_ignores_bot_and_other_requestees():
    flags = [
        # Our own reminders must not restart the countdown.
        needinfo_flag(BOT, AUTHOR, "2026-08-26T10:00:00Z"),
        # A needinfo on somebody else is not the author's deadline.
        needinfo_flag(SHERIFF, "someone@mozilla.com", "2026-08-25T10:00:00Z"),
        # A needinfo without a requestee must not raise.
        {
            "name": "needinfo",
            "status": "?",
            "setter": SHERIFF,
            "creation_date": "2026-08-25T10:00:00Z",
            "modification_date": "2026-08-25T10:00:00Z",
        },
    ]

    assert PerfAlertBackoutWarning.get_needinfo_date(flags, AUTHOR) is None


def test_get_needinfo_date_without_flags():
    assert PerfAlertBackoutWarning.get_needinfo_date([], AUTHOR) is None


TODAY = "2026-08-26"
# Two business days before TODAY.
NI_DATE = "2026-08-24T10:00:00Z"


def make_bug(bug_id, author=AUTHOR, creator="reporter@mozilla.com", ni_date=NI_DATE):
    bug = {
        "id": str(bug_id),
        "creator": creator,
        "regressor_id": 1000 + bug_id,
        "needinfo_flags": [needinfo_flag(SHERIFF, AUTHOR, ni_date)],
    }
    if author is not None:
        bug["regressor_author_email"] = author
    return bug


class FakeBugzilla:
    comments: dict[str, list[str]] = {}

    def __init__(self, bugids, commenthandler, **kwargs):
        self.bugids = bugids
        self.commenthandler = commenthandler

    def get_data(self):
        return self

    def wait(self):
        for bug_id in self.bugids:
            self.commenthandler(
                {"comments": [{"creator": c} for c in self.comments.get(bug_id, [])]},
                bug_id,
            )


def active_user(blocked=False):
    return {
        "status": UserStatus.ACTIVE,
        "requests": {"needinfo": {"blocked": blocked}},
    }


@pytest.fixture
def rule(monkeypatch):
    monkeypatch.setattr(perfalert_backout_warning, "Bugzilla", FakeBugzilla)
    monkeypatch.setattr(
        perfalert_backout_warning.lmdutils, "get_date", lambda *a, **k: TODAY
    )
    FakeBugzilla.comments = {}
    users = {AUTHOR: active_user()}

    class FakeUserActivity:
        def __init__(self, **kwargs):
            pass

        def check_users(self, emails, **kwargs):
            return {e: users[e] for e in emails if e in users}

    monkeypatch.setattr(perfalert_backout_warning, "UserActivity", FakeUserActivity)
    instance = PerfAlertBackoutWarning()
    instance.users = users
    return instance


def test_filter_bugs_keeps_bug_at_deadline(rule):
    bugs = rule.filter_bugs({"1": make_bug(1)})

    assert list(bugs) == ["1"]


def test_filter_bugs_drops_bug_outside_deadline(rule):
    bugs = rule.filter_bugs(
        {
            "1": make_bug(1, ni_date="2026-08-25T10:00:00Z"),
            "2": make_bug(2, ni_date="2026-08-21T10:00:00Z"),
            "3": make_bug(3),
        }
    )

    assert list(bugs) == ["3"]


def test_filter_bugs_drops_bug_without_regressor_author(rule):
    bugs = rule.filter_bugs(
        {
            "1": make_bug(1, author="nobody@mozilla.org"),
            "2": make_bug(2, author=None),
            "3": make_bug(3),
        }
    )

    assert list(bugs) == ["3"]


def test_filter_bugs_drops_bug_created_by_regressor_author(rule):
    bugs = rule.filter_bugs({"1": make_bug(1, creator=AUTHOR), "2": make_bug(2)})

    assert list(bugs) == ["2"]


def test_filter_bugs_drops_bug_where_author_commented(rule):
    FakeBugzilla.comments = {"1": [AUTHOR]}

    bugs = rule.filter_bugs({"1": make_bug(1), "2": make_bug(2)})

    assert list(bugs) == ["2"]


def test_filter_bugs_drops_bug_with_unknown_author(rule):
    # The author is missing from the user activity result.
    rule.users.clear()

    assert rule.filter_bugs({"1": make_bug(1)}) == {}


def test_filter_bugs_drops_inactive_or_blocked_author(rule):
    rule.users[AUTHOR] = active_user(blocked=True)
    assert rule.filter_bugs({"1": make_bug(1)}) == {}

    rule.users[AUTHOR] = {**active_user(), "status": UserStatus.DISABLED}
    assert rule.filter_bugs({"1": make_bug(1)}) == {}
