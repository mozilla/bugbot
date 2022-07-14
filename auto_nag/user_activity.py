# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import timedelta
from enum import Enum, auto
from typing import List

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import BugzillaUser
from libmozdata.connection import Connection
from libmozdata.phabricator import PhabricatorAPI
from tenacity import retry, stop_after_attempt, wait_exponential

from auto_nag import utils
from auto_nag.people import People

# The chunk size here should not be more than 100; which is the maximum number of
# items that Phabricator could return in one response.
PHAB_CHUNK_SIZE = 100


class UserStatus(Enum):
    ACTIVE = auto()
    UNDEFINED = auto()
    DISABLED = auto()
    INACTIVE = auto()
    ABSENT = auto()
    UNAVAILABLE = auto()


class UserActivity:
    """Check the user activity on Bugzilla and Phabricator"""

    def __init__(
        self,
        activity_weeks_count: int = 26,
        absent_weeks_count: int = 26,
        unavailable_max_days: int = 7,
        include_fields: list = None,
        phab: PhabricatorAPI = None,
    ) -> None:
        """
        Constructor

        Args:
            activity_weeks_count: the number of weeks since last made a change
                to a bug before a user being considered as inactive.
            absent_weeks_count: the number of weeks since last loaded any page
                from Bugzilla before a user being considered as inactive.
            unavailable_max_days: a user will be considered inactive if they
                have more days left to be available than `unavailable_max_days`.
            include_fields: the list of fields to include with the the Bugzilla
                user object.
            phab: if an instance of PhabricatorAPI is not provided, it will be
                created when it is needed.
        """
        self.activity_weeks_count = activity_weeks_count
        self.absent_weeks_count = absent_weeks_count
        self.include_fields = include_fields or []
        self.people = People.get_instance()
        self.phab = phab
        self.availability_limit = (
            lmdutils.get_date_ymd("today") + timedelta(unavailable_max_days)
        ).timestamp()

        self.activity_limit = lmdutils.get_date("today", self.activity_weeks_count * 7)
        self.seen_limit = lmdutils.get_date("today", self.absent_weeks_count * 7)

    def _get_phab(self):
        if not self.phab:
            self.phab = PhabricatorAPI(utils.get_login_info()["phab_api_key"])

        return self.phab

    def check_users(self, user_emails: List[str]) -> dict:
        """Check user activity using their Bugzilla emails"""

        # Employees will always be considered active
        user_emails = self._get_not_employees(user_emails)

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

        user_statuses.update(self.get_bz_users_with_status(user_emails))

        return user_statuses

    def _get_not_employees(self, user_emails):
        return [
            user_email
            for user_email in user_emails
            if not self.people.is_mozilla(user_email)
        ]

    def _get_status_from_bz_user(self, user: dict) -> UserStatus:
        if not user["can_login"]:
            return UserStatus.DISABLED

        if user["last_seen_date"] is None or user["last_seen_date"] < self.seen_limit:
            return UserStatus.ABSENT

        if (
            user["last_activity_time"] is None
            or user["last_activity_time"] < self.activity_limit
        ):
            return UserStatus.INACTIVE

        return UserStatus.ACTIVE

    def get_bz_users_with_status(
        self, id_or_name: list, keep_active: bool = False
    ) -> dict:
        """Get Bugzilla users with their activity statuses.

        Args:
            id_or_name: An integer user ID or login name of the user on
                bugzilla.
            keep_active: whether the returned results should include the active
                users.

        Returns:
            A dictionary where the key is the user login name and the value is
            the user info with the status.
        """

        def handler(user, data):
            status = self._get_status_from_bz_user(user)
            if keep_active or status == UserStatus.ACTIVE:
                user["status"] = status
                data[user["name"]] = user

        users: dict = {}
        BugzillaUser(
            user_data=users,
            user_names=id_or_name,
            user_handler=handler,
            include_fields=[
                "name",
                "can_login",
                "last_activity_time",
                "last_seen_date",
            ]
            + self.include_fields,
        ).wait()

        return users

    def _get_status_from_phab_user(self, user: dict) -> UserStatus:
        availability = user["attachments"]["availability"]
        if availability["value"] != "available":
            # We do not need to consider the user inactive they will be
            # available again soon.
            if (
                not availability["until"]
                or availability["until"] > self.availability_limit
            ):
                return UserStatus.UNAVAILABLE

        return UserStatus.ACTIVE

    def get_phab_users_with_status(
        self, user_phids: List[str], keep_active: bool = False
    ) -> dict:
        """Get Phabricator users with their activity statuses.

        Args:
            user_phids: A list of user PHIDs.
            keep_active: whether the returned results should include the active
                users.

        Returns:
            A dictionary where the key is the user PHID and the value is
            the user info with the status.
        """

        bzid_to_phid = {
            int(user["id"]): user["phid"]
            for _user_phids in Connection.chunks(user_phids, PHAB_CHUNK_SIZE)
            for user in self._fetch_bz_user_ids(user_phids=_user_phids)
        }
        if not bzid_to_phid:
            return {}

        if "id" not in self.include_fields:
            self.include_fields.append("id")

        user_bz_ids = list(bzid_to_phid.keys())
        users = self.get_bz_users_with_status(user_bz_ids, keep_active=True)
        users = {bzid_to_phid[user["id"]]: user for user in users.values()}

        # To cover cases where a person is temporary off (e.g., long PTO), we
        # will rely on the calendar from phab.
        for _user_phids in Connection.chunks(user_phids, PHAB_CHUNK_SIZE):
            for phab_user in self._fetch_phab_users(_user_phids):
                user = users[phab_user["phid"]]
                if user["status"] == UserStatus.ACTIVE:
                    user["status"] = self._get_status_from_phab_user(phab_user)

                if not keep_active and user["status"] == UserStatus.ACTIVE:
                    del users[phab_user["phid"]]
                    continue

                user["phab_username"] = phab_user["fields"]["username"]

        return users

    def get_string_status(self, status: UserStatus):
        """Get a string representation of the user status."""

        if status == UserStatus.UNDEFINED:
            return "Not specified"
        if status == UserStatus.DISABLED:
            return "Account disabled"
        if status == UserStatus.INACTIVE:
            return f"Inactive on Bugzilla in last {self.activity_weeks_count} weeks"
        if status == UserStatus.ABSENT:
            return f"Not seen on Bugzilla in last {self.absent_weeks_count} weeks"

        return status.name

    @retry(
        wait=wait_exponential(min=4),
        stop=stop_after_attempt(5),
    )
    def _fetch_phab_users(self, phids: list):
        if len(phids) == 0:
            return []

        return self._get_phab().search_users(
            constraints={"phids": phids},
            attachments={"availability": True},
        )

    @retry(
        wait=wait_exponential(min=4),
        stop=stop_after_attempt(5),
    )
    def _fetch_bz_user_ids(self, *args, **kwargs):
        return self._get_phab().load_bz_account(*args, **kwargs)
