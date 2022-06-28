# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from enum import Enum, auto

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import BugzillaUser

from auto_nag import utils
from auto_nag.people import People

DEFAULT_ACTIVITY_WEEKS = 26
DEFAULT_ABSENT_WEEKS = 26


class UserStatus(Enum):
    UNDEFINED = auto()
    DISABLED = auto()
    INACTIVE = auto()
    ABSENT = auto()


class UserActivity:
    def __init__(
        self,
        activity_weeks_count=DEFAULT_ACTIVITY_WEEKS,
        absent_weeks_count=DEFAULT_ABSENT_WEEKS,
        include_fields=[],
    ) -> None:
        self.activity_weeks_count = activity_weeks_count
        self.absent_weeks_count = absent_weeks_count
        self.include_fields = include_fields
        self.people = People.get_instance()

        self.activity_limit = lmdutils.get_date("today", self.activity_weeks_count * 7)
        self.seen_limit = lmdutils.get_date("today", self.absent_weeks_count * 7)

    def check_users(self, user_emails):
        # Employees will always be considered active
        user_emails = self.get_not_employees(user_emails)

        user_statuses = {
            user_email: {"status": UserStatus.UNDEFINED}
            for user_email in user_emails
            if utils.is_no_assignee(user_email)
        }
        if len(user_emails) == len(user_statuses):
            return user_statuses

        user_emails = [
            user_email for user_email in user_emails if user_email not in user_statuses
        ]

        return self.get_bz_status(user_emails, user_statuses)

    def get_not_employees(self, user_emails):
        return [
            user_email
            for user_email in user_emails
            if not self.people.is_mozilla(user_email)
        ]

    def get_bz_status(self, user_emails, user_statuses={}):
        def handler(user, data):
            if not user["can_login"]:
                user["status"] = UserStatus.DISABLED
            elif (
                user["last_seen_date"] is None
                or user["last_seen_date"] < self.seen_limit
            ):
                user["status"] = UserStatus.ABSENT
            elif (
                user["last_activity_time"] is None
                or user["last_activity_time"] < self.activity_limit
            ):
                user["status"] = UserStatus.INACTIVE
            else:
                return

            data[user["name"]] = user

        BugzillaUser(
            user_data=user_statuses,
            user_names=user_emails,
            user_handler=handler,
            include_fields=[
                "name",
                "can_login",
                "last_activity_time",
                "last_seen_date",
            ]
            + self.include_fields,
        ).wait()

        return user_statuses

    def get_string_status(self, status: UserStatus):
        if status == UserStatus.UNDEFINED:
            return "Not specified"
        elif status == UserStatus.DISABLED:
            return "Account disabled"
        elif status == UserStatus.INACTIVE:
            return f"Inactive on Bugzilla in last {self.activity_weeks_count} weeks"
        elif status == UserStatus.ABSENT:
            return f"Not seen on Bugzilla in last {self.absent_weeks_count} weeks"
        else:
            return status.name
