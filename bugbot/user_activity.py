# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from datetime import timedelta
from enum import Enum, auto
from typing import Iterable, List, Optional

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import BugzillaUser
from libmozdata.connection import Connection
from libmozdata.phabricator import PhabricatorAPI
from tenacity import retry, stop_after_attempt, wait_exponential

from bugbot import utils
from bugbot.people import People

logging.basicConfig(level=logging.DEBUG)

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
    INACTIVE_NEW = auto()
    ABSENT_NEW = auto()


class UserActivity:
    """Check the user activity on Bugzilla and Phabricator"""

    def __init__(
        self,
        activity_weeks_count: int = 26,
        absent_weeks_count: int = 26,
        new_user_weeks_count: int = 4,
        unavailable_max_days: int = 7,
        include_fields: list | None = None,
        phab: PhabricatorAPI | None = None,
        people: People | None = None,
        reference_date: str = "today",
    ) -> None:
        """
        Constructor

        Args:
            activity_weeks_count: the number of weeks since last made a change
                to a bug before a user being considered as inactive.
            absent_weeks_count: the number of weeks since last loaded any page
                from Bugzilla before a user being considered as inactive.
            new_user_weeks_count: the number of weeks since last made a change
                to a bug before a new user being considered as inactive.
            unavailable_max_days: a user will be considered inactive if they
                have more days left to be available than `unavailable_max_days`.
            include_fields: the list of fields to include with the the Bugzilla
                user object.
            phab: if an instance of PhabricatorAPI is not provided, it will be
                created when it is needed.
            people: if an instance of People is not provided, the global
                instance will be used.
            reference_date: the reference date to use for checking user
                activity. This is needed for testing because the dates in the
                mock data are fixed.
        """
        self.activity_weeks_count = activity_weeks_count
        self.absent_weeks_count = absent_weeks_count
        self.new_user_weeks_count = new_user_weeks_count
        self.include_fields = include_fields or []
        self.people = people if people is not None else People.get_instance()
        self.phab = phab
        self.availability_limit = (
            lmdutils.get_date_ymd(reference_date) + timedelta(unavailable_max_days)
        ).timestamp()

        self.activity_limit = lmdutils.get_date(
            reference_date, self.activity_weeks_count * 7
        )
        self.activity_limit_ts = lmdutils.get_date_ymd(self.activity_limit).timestamp()
        self.seen_limit = lmdutils.get_date(reference_date, self.absent_weeks_count * 7)

        self.new_user_activity_limit = lmdutils.get_date(
            reference_date, self.new_user_weeks_count * 7
        )
        self.new_user_activity_limit_ts = lmdutils.get_date_ymd(
            self.new_user_activity_limit
        ).timestamp()
        self.new_user_seen_limit = lmdutils.get_date(
            reference_date, self.new_user_weeks_count * 7
        )

        # Bugzilla accounts younger than 61 days are considered new users
        self.new_user_limit = lmdutils.get_date(reference_date, 61)

    def _get_phab(self):
        if not self.phab:
            self.phab = PhabricatorAPI(utils.get_login_info()["phab_api_key"])

        return self.phab

    def check_users(
        self,
        user_emails: Iterable[str],
        keep_active: bool = False,
        ignore_bots: bool = False,
        fetch_employee_info: bool = False,
    ) -> dict:
        """Check user activity using their emails

        Args:
            user_emails: the email addresses of the users.
            keep_active: whether the returned results should include the active
                users.
            ignore_bots: whether the returned results should include bot and
                component-watching accounts.
            fetch_employee_info: whether to fetch the employee info from
                Bugzilla. Only fields specified in `include_fields` will be
                guaranteed to be fetched.

        Returns:
            A dictionary where the key is the user email and the value is the
                user info with the status.
        """

        user_statuses = {
            user_email: {
                "status": (
                    UserStatus.UNDEFINED
                    if utils.is_no_assignee(user_email)
                    else UserStatus.ACTIVE
                ),
                "is_employee": self.people.is_mozilla(user_email),
            }
            for user_email in user_emails
            if not ignore_bots or not utils.is_bot_email(user_email)
        }

        # Employees will always be considered active
        user_emails = [
            user_email
            for user_email, info in user_statuses.items()
            if not info["is_employee"] and info["status"] == UserStatus.ACTIVE
        ]

        if not keep_active:
            user_statuses = {
                user_email: info
                for user_email, info in user_statuses.items()
                if info["status"] != UserStatus.ACTIVE
            }

        if fetch_employee_info:
            employee_emails = [
                user_email
                for user_email, info in user_statuses.items()
                if info["is_employee"]
            ]
            if employee_emails:
                BugzillaUser(
                    user_names=employee_emails,
                    user_data=user_statuses,
                    user_handler=lambda user, data: data[user["name"]].update(user),
                    include_fields=self.include_fields + ["name"],
                ).wait()

        if user_emails:
            user_statuses.update(
                self.get_bz_users_with_status(user_emails, keep_active)
            )

        return user_statuses

    def get_status_from_bz_user(self, user: dict) -> UserStatus:
        """Get the user status from a Bugzilla user object."""
        is_new_user = user["creation_time"] > self.new_user_limit

        seen_limit = self.seen_limit if not is_new_user else self.new_user_seen_limit
        activity_limit = (
            self.activity_limit if not is_new_user else self.new_user_activity_limit
        )

        if not user["can_login"]:
            return UserStatus.DISABLED

        if user["creation_time"] > seen_limit:
            return UserStatus.ACTIVE

        if user["last_seen_date"] is None or user["last_seen_date"] < seen_limit:
            return UserStatus.ABSENT_NEW if is_new_user else UserStatus.ABSENT

        if (
            user["last_activity_time"] is None
            or user["last_activity_time"] < activity_limit
        ):
            return UserStatus.INACTIVE_NEW if is_new_user else UserStatus.INACTIVE

        return UserStatus.ACTIVE

    def get_bz_users_with_status(
        self, id_or_name: list, keep_active: bool = True
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
            status = self.get_status_from_bz_user(user)
            if keep_active or status != UserStatus.ACTIVE:
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
                "creation_time",
            ]
            + self.include_fields,
        ).wait()

        return users

    def _get_status_from_phab_user(self, user: dict) -> Optional[UserStatus]:
        if "disabled" in user["fields"]["roles"]:
            return UserStatus.DISABLED

        availability = user["attachments"]["availability"]
        if availability["value"] != "available":
            # We do not need to consider the user inactive they will be
            # available again soon.
            if (
                not availability["until"]
                or availability["until"] > self.availability_limit
            ):
                return UserStatus.UNAVAILABLE

        return None

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
                try:
                    user = users[phab_user["phid"]]
                    phab_status = self._get_status_from_phab_user(phab_user)
                    if phab_status:
                        user["status"] = phab_status

                    elif user["status"] in (
                        UserStatus.ABSENT,
                        UserStatus.INACTIVE,
                    ) and self.is_active_on_phab(phab_user["phid"]):
                        user["status"] = UserStatus.ACTIVE

                    if not keep_active and user["status"] == UserStatus.ACTIVE:
                        del users[phab_user["phid"]]
                        continue

                    user["phab_username"] = phab_user["fields"]["username"]
                    user["unavailable_until"] = phab_user["attachments"][
                        "availability"
                    ]["until"]
                except KeyError as e:
                    logging.error(
                        f"Error fetching inactive patch authors: '{phab_user['phid']}' - {str(e)}"
                    )
                    continue

        return users

    def is_active_on_phab(self, user_phid: str) -> bool:
        """Check if the user has recent activities on Phabricator.

        Args:
            user_phid: The user PHID.

        Returns:
            True if the user is active on Phabricator, False otherwise.
        """

        feed = self._get_phab().request(
            "feed.query",
            filterPHIDs=[user_phid],
            limit=1,
        )
        for story in feed.values():
            if story["epoch"] >= self.activity_limit_ts:
                return True

        return False

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
        if status == UserStatus.INACTIVE_NEW:
            return f"Inactive on Bugzilla in last {self.new_user_weeks_count} weeks (new user)"
        if status == UserStatus.ABSENT_NEW:
            return f"Not seen on Bugzilla in last {self.new_user_weeks_count} weeks (new user)"

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
