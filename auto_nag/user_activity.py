# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from enum import Enum

from libmozdata.bugzilla import Bugzilla, BugzillaUser

from auto_nag import utils
from auto_nag.people import People

DEFAULT_ACTIVITY_WEEKS = 26


class UserStatus(Enum):
    UNDEFINED = 1
    DISABLED = 2
    INACTIVE = 3


class UserActivity:
    def __init__(self, weeks_count=DEFAULT_ACTIVITY_WEEKS) -> None:
        self.weeks_count = weeks_count
        self.people = People.get_instance()

    def check_users(self, user_emails):
        user_emails = self.get_not_employees(user_emails)

        none_users = {
            user_email for user_email in user_emails if utils.is_no_assignee(user_email)
        }
        user_emails.difference_update(none_users)
        status = {user_email: UserStatus.UNDEFINED for user_email in none_users}
        if len(user_emails) == 0:
            return status

        disabled_users = self.get_disabled_users(user_emails)
        user_emails.difference_update(disabled_users)
        for user_email in disabled_users:
            status[user_email] = UserStatus.DISABLED

        for user_email in user_emails:
            if self.is_inactive_user(user_email):
                status[user_email] = UserStatus.INACTIVE

        return status

    def get_not_employees(self, user_emails):
        return {
            user_email
            for user_email in user_emails
            if not self.people.is_mozilla(user_email)
        }

    def is_inactive_user(self, user_email):
        bugs = {"count": 0}

        params = {
            "limit": 1,
            "f1": "anything",
            "o1": "changedby",
            "v1": user_email,
            "f2": "anything",
            "o2": "changedafter",
            "v2": f"-{self.weeks_count}w",
        }

        def handle_bugs(_, data):
            data["count"] += 1

        Bugzilla(
            params, include_fields=["id"], bughandler=handle_bugs, bugdata=bugs
        ).wait()

        return bugs["count"] == 0

    def get_disabled_users(self, user_emails):
        def handler(user, data):
            if not user["can_login"]:
                data.add(user["name"])

        data = set()
        user_emails = (
            user_emails if isinstance(user_emails, list) else list(user_emails)
        )

        step = 200
        start = 0
        end = start + step
        while start < len(user_emails):
            chunk = user_emails[start:end]
            BugzillaUser(
                user_data=data,
                user_names=chunk,
                user_handler=handler,
                include_fields=["name", "can_login"],
            ).wait()
            start, end = end, end + step

        return data

    def is_disabled_user(self, user_email):
        users = self.get_disabled_users([user_email])
        return user_email in users

    def get_string_status(self, status: UserStatus):
        if status == UserStatus.UNDEFINED:
            return "Not assigned"
        elif status == UserStatus.DISABLED:
            return "Account disabled"
        elif status == UserStatus.INACTIVE:
            return f"Inactive on Bugzilla in last {self.weeks_count} weeks"
        else:
            return status.name
