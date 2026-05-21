# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
import responses
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import BugzillaUser

from bugbot.people import People
from bugbot.user_activity import UserActivity, UserStatus

REFERENCE_DATE = "2022-08-18"

ACTIVE_USERS = {"smujahid@mozilla.com", "mcastelluccio@mozilla.com"}

DISABLED_USERS = {
    "bdahl@mozilla.com",
    "u709243@disabled.tld",
    "balbeza@mozilla.com",
}

BOTS = {
    "sheriffs@mozilla.bugs",  # component watching account
    "release-mgmt-account-bot@mozilla.tld",  # bot account
    "orangefactor@bots.tld",  # bot account
}


@pytest.fixture
def user_activity_employees():
    return {"abc@mozilla.com", "def@mozilla.com"}


@pytest.fixture
def user_activity_people(user_activity_employees):
    return People(
        [
            {
                "mail": email,
                # Dummy info to satisfy the Person type
                "bugzillaEmail": "",
                "bugzillaID": "",
                "cn": "",
                "dn": "mail=xx@mozilla.com,o=com,dc=mozilla",
                "found_on_bugzilla": True,
                "im": [],
                "isdirector": "FALSE",
                "ismanager": "FALSE",
                "manager": {"cn": "", "dn": "mail=xxx@mozilla.com,o=com,dc=mozilla"},
                "title": "",
            }
            for email in user_activity_employees
        ]
    )


@pytest.fixture
def bugzilla_user_mock(setup_mock_urls):
    setup_mock_urls([BugzillaUser.URL])


@responses.activate
def test_check_users(bugzilla_user_mock, user_activity_people, user_activity_employees):
    """Test the check_users method"""

    user_activity = UserActivity(
        people=user_activity_people, reference_date=REFERENCE_DATE
    )
    inactive_users = user_activity.check_users(
        ACTIVE_USERS | DISABLED_USERS | user_activity_employees
    )

    assert inactive_users.keys() == DISABLED_USERS


@responses.activate
def test_check_users_keep_active(
    bugzilla_user_mock, user_activity_people, user_activity_employees
):
    """Test the check_users method with keep_active set to True"""

    user_activity = UserActivity(
        people=user_activity_people, reference_date=REFERENCE_DATE
    )
    users_info = user_activity.check_users(
        ACTIVE_USERS | DISABLED_USERS | user_activity_employees, keep_active=True
    )

    for email in ACTIVE_USERS:
        assert email in users_info

        user = users_info[email]
        assert "is_employee" not in user
        assert user["status"] == UserStatus.ACTIVE

    for email in user_activity_employees:
        assert email in users_info

        user = users_info[email]
        assert user["is_employee"] is True
        assert user["status"] == UserStatus.ACTIVE

    for email in DISABLED_USERS:
        assert email in users_info

        user = users_info[email]
        assert "is_employee" not in user
        assert user["status"] == UserStatus.DISABLED


@responses.activate
def test_check_users_ignore_bots(bugzilla_user_mock, user_activity_people):
    user_activity = UserActivity(
        people=user_activity_people, reference_date=REFERENCE_DATE
    )
    users_info = user_activity.check_users(
        BOTS | DISABLED_USERS, ignore_bots=True, keep_active=True
    )

    for email in BOTS:
        assert email not in users_info.keys()

    for email in DISABLED_USERS:
        assert email in users_info.keys()

    users_info = user_activity.check_users(
        BOTS | DISABLED_USERS, ignore_bots=False, keep_active=True
    )

    for email in BOTS:
        assert email in users_info.keys()

    for email in DISABLED_USERS:
        assert email in users_info.keys()


@responses.activate
def test_get_bz_users_with_status(bugzilla_user_mock, user_activity_people):
    """Test the get_bz_users_with_status method"""

    user_activity = UserActivity(
        people=user_activity_people,
        include_fields=["nick", "id"],
        reference_date=REFERENCE_DATE,
    )
    users_info = user_activity.get_bz_users_with_status(
        list(ACTIVE_USERS | DISABLED_USERS)
    )

    for email in ACTIVE_USERS:
        assert email in users_info

        user = users_info[email]
        assert "nick" in user
        assert "id" in user
        assert user["status"] == UserStatus.ACTIVE

    for email in DISABLED_USERS:
        assert email in users_info

        user = users_info[email]
        assert "nick" in user
        assert "id" in user
        assert user["status"] == UserStatus.DISABLED

    user = users_info["bdahl@mozilla.com"]
    assert user["id"] == 425126
    assert user["nick"] == "bdahl"


def test_get_status_from_bz_user(user_activity_people):
    """Test the get_status_from_bz_user method"""

    user_activity = UserActivity(
        people=user_activity_people, include_fields=["nick", "id"]
    )

    new_user = {
        "creation_time": lmdutils.get_date("yesterday"),
        "last_activity_time": None,
        "last_seen_date": None,
        "can_login": True,
    }
    status = user_activity.get_status_from_bz_user(new_user)
    assert status == UserStatus.ACTIVE

    old_user = {
        "creation_time": "1970-09-14T11:33:10Z",
        "last_activity_time": None,
        "last_seen_date": None,
        "can_login": True,
    }
    status = user_activity.get_status_from_bz_user(old_user)
    assert status == UserStatus.ABSENT
