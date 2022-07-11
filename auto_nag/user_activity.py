# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import timedelta
from enum import Enum, auto

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import BugzillaUser
from libmozdata.connection import Connection
from libmozdata.phabricator import PhabricatorAPI
from tenacity import retry, stop_after_attempt, wait_exponential

from auto_nag import utils
from auto_nag.people import People

DEFAULT_ACTIVITY_WEEKS = 26
DEFAULT_ABSENT_WEEKS = 26


# The chunk size her should not be more than 100; which is the maximum number of
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
    def __init__(
        self,
        activity_weeks_count=DEFAULT_ACTIVITY_WEEKS,
        absent_weeks_count=DEFAULT_ABSENT_WEEKS,
        include_fields=[],
        unavailable_max_days: int = 7,
    ) -> None:
        self.activity_weeks_count = activity_weeks_count
        self.absent_weeks_count = absent_weeks_count
        self.include_fields = include_fields
        self.people = People.get_instance()
        self.phab = None
        self.availability_limit = (
            lmdutils.get_date_ymd("today") + timedelta(unavailable_max_days)
        ).timestamp()

        self.activity_limit = lmdutils.get_date("today", self.activity_weeks_count * 7)
        self.seen_limit = lmdutils.get_date("today", self.absent_weeks_count * 7)

    def _get_phab(self):
        if not self.phab:
            self.phab = PhabricatorAPI(utils.get_login_info()["phab_api_key"])

        return self.phab

    def check_users(self, user_emails) -> dict:
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

        user_statuses.update(self.get_bz_users_with_status(user_emails))

        return user_statuses

    def get_not_employees(self, user_emails):
        return [
            user_email
            for user_email in user_emails
            if not self.people.is_mozilla(user_email)
        ]

    def get_bz_users_with_status(
        self, user_names: list, keep_active: bool = False
    ) -> dict:
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
            elif keep_active:
                user["status"] = UserStatus.ACTIVE
            else:
                return

            data[user["name"]] = user

        users: dict = {}
        BugzillaUser(
            user_data=users,
            user_names=user_names,
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

    def get_phab_users_with_status(self, user_phids: list, keep_active: bool = False):
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
        user_phids = [
            phid for phid, user in users.items() if user["status"] == UserStatus.ACTIVE
        ]

        for _user_phids in Connection.chunks(user_phids, PHAB_CHUNK_SIZE):
            for phab_user in self._fetch_phab_users(_user_phids):
                availability = phab_user["attachments"]["availability"]
                if availability["value"] != "available" and (
                    not availability["until"]
                    or availability["until"] > self.availability_limit
                ):
                    status = UserStatus.UNAVAILABLE
                elif keep_active:
                    status = UserStatus.ACTIVE
                else:
                    del users[phab_user["phid"]]
                    continue

                user = users[phab_user["phid"]]
                user["status"] = status

        return users

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
