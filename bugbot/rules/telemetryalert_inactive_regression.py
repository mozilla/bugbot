# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import collections

from libmozdata.bugzilla import Bugzilla
from libmozdata.bugzilla import BugzillaUser

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.user_activity import UserActivity, UserStatus


class TelemetryAlertInactiveRegression(BzCleaner):
    def __init__(self, nweeks=1):
        super().__init__()
        self.nweeks = nweeks
        self.extra_ni = {"nweeks": self.nweeks}

    def description(self):
        return f"Telemetry alerts with {self.nweeks} week(s) of inactivity"

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def get_extra_for_template(self):
        return self.extra_ni

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        fields = [
            "id",
            "history",
        ]

        # Find all bugs that have a telemetry-alert keyword, have not changed in the
        # last week, and do not have the backlog-deferred keyword set
        params = {
            "include_fields": fields,
            "f3": "keywords",
            "o3": "allwords",
            "v3": ["telemetry-alert"],
            "f4": "keywords",
            "o4": "nowords",
            "v4": "backlog-deferred",
            "f5": "days_elapsed",
            "o5": "greaterthan",
            "v5": self.nweeks * 7,
            "status": ["UNCONFIRMED", "NEW", "REOPENED"],
            "resolution": ["---"],
        }

        return params


    def get_probe_owner(self, bug_history):
        probe_owner = ""

        for change in bug_history:
            # Skip history changes when they are not from the intermittent bug filer
            # since it's responsible for adding the first needinfo for the probe owner
            if change["who"] != "intermittent-bug-filer@mozilla.bugs":
                continue

            # Use the CC field entry to find the email of the person that should
            # be needinfo'ed so we don't need to parse it from the needinfo change
            needinfo_found = False
            for specific_change in change["changes"]:
                if (
                    specific_change["field_name"] == "flagtypes.name"
                    and "needinfo" in specific_change["added"]
                ):
                    needinfo_found = True
                elif specific_change["field_name"] == "cc":
                    probe_owner = specific_change["added"]

            if needinfo_found:
                break

        return probe_owner


    def handle_bug(self, bug, data):
        probe_owner = self.get_probe_owner(bug["history"])
        if not probe_owner:
            # Could not find a probe owner for some reason
            return

        data[str(bug["id"])] = { "probe_owner": probe_owner }

        return bug

    def get_needinfo_nicks(self, bugs):
        def _user_handler(user, data):
            data[user["name"]] = user["nick"]

        authors_to_ni = set()
        for bug_info in bugs.values():
            authors_to_ni.add(bug_info["probe_owner"])

        if not authors_to_ni:
            return

        user_emails_to_names = {}
        BugzillaUser(
            user_names=list(authors_to_ni),
            include_fields=["nick", "name"],
            user_handler=_user_handler,
            user_data=user_emails_to_names,
        ).wait()

        for bug_info in bugs.values():
            bug_info["nickname"] = user_emails_to_names[bug_info["probe_owner"]]


    def filter_bugs(self, bugs):
        # Exclude bugs where the regressor author is inactive or blocked needinfo.
        # TODO: We can drop this when https://github.com/mozilla/bugbot/issues/1465 is implemented.
        users_info = UserActivity(include_fields=["groups", "requests"]).check_users(
            set(bug["probe_owner"] for bug in bugs.values()),
            keep_active=True,
            fetch_employee_info=True,
        )

        for bug_id, bug in list(bugs.items()):
            user_info = users_info[bug["probe_owner"]]
            if (
                user_info["status"] != UserStatus.ACTIVE
                or user_info["requests"]["needinfo"]["blocked"]
            ):
                del bugs[bug_id]

        return bugs

    def set_autofix(self, bugs):
        for bugid, info in bugs.items():
            self.add_auto_ni(
                bugid,
                {
                    "mail": info["probe_owner"],
                    "nickname": info["nickname"],
                },
            )

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        self.get_needinfo_nicks(bugs)
        self.filter_bugs(bugs)
        self.set_autofix(bugs)
        return bugs


if __name__ == "__main__":
    TelemetryAlertInactiveRegression().run()
