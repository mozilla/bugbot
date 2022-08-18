# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import responses
from libmozdata.bugzilla import BugzillaUser

from auto_nag.auto_mock import MockTestCase
from auto_nag.people import People
from auto_nag.user_activity import UserActivity, UserStatus


class UserActivityTest(MockTestCase):
    """Test the UserActivity class"""

    mock_urls = [BugzillaUser.URL]

    active_users = {"smujahid@mozilla.com", "mcastelluccio@mozilla.com"}

    disabled_users = {
        "bdahl@mozilla.com",
        "u709243@disabled.tld",
        "balbeza@mozilla.com",
    }

    employees = {"abc@mozilla.com", "def@mozilla.com"}

    people = People([{"mail": email} for email in employees])

    @responses.activate
    def test_check_users(self):
        """Test the check_users method"""

        user_activity = UserActivity(people=self.people)
        inactive_users = user_activity.check_users(
            self.active_users | self.disabled_users | self.employees
        )

        self.assertEqual(inactive_users.keys(), self.disabled_users)

    @responses.activate
    def test_check_users_keep_active(self):
        """Test the check_users method with keep_active set to True"""

        user_activity = UserActivity(people=self.people)
        users_info = user_activity.check_users(
            self.active_users | self.disabled_users | self.employees, keep_active=True
        )

        for email in self.active_users:
            self.assertIn(email, users_info)

            user = users_info[email]
            self.assertNotIn("is_employee", user)
            self.assertEqual(user["status"], UserStatus.ACTIVE)

        for email in self.employees:
            self.assertIn(email, users_info)

            user = users_info[email]
            self.assertEqual(user["is_employee"], True)
            self.assertEqual(user["status"], UserStatus.ACTIVE)

        for email in self.disabled_users:
            self.assertIn(email, users_info)

            user = users_info[email]
            self.assertNotIn("is_employee", user)
            self.assertEqual(user["status"], UserStatus.DISABLED)

    @responses.activate
    def test_get_bz_users_with_status(self):
        """Test the get_bz_users_with_status method"""

        user_activity = UserActivity(people=self.people, include_fields=["nick", "id"])
        users_info = user_activity.get_bz_users_with_status(
            list(self.active_users | self.disabled_users)
        )

        for email in self.active_users:
            self.assertIn(email, users_info)

            user = users_info[email]
            self.assertIn("nick", user)
            self.assertIn("id", user)
            self.assertEqual(user["status"], UserStatus.ACTIVE)

        for email in self.disabled_users:
            self.assertIn(email, users_info)

            user = users_info[email]
            self.assertIn("nick", user)
            self.assertIn("id", user)
            self.assertEqual(user["status"], UserStatus.DISABLED)

        user = users_info["bdahl@mozilla.com"]
        self.assertEqual(user["id"], 425126)
        self.assertEqual(user["nick"], "bdahl")
