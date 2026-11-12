# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import date

from bugbot.rules.perfalert_backout_warning import PerfAlertBackoutWarning

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
