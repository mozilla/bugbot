# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import dateutil.parser
from libmozdata.bugzilla import Bugzilla, BugzillaUser

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.rules.needinfo_regression_author import NeedinfoRegressionAuthor


class PerfAlertInactiveRegressionNag(NeedinfoRegressionAuthor):
    def __init__(self, nweeks: int = 1):
        super().__init__()
        self.nweeks = nweeks

    def description(self):
        return "PerfAlert regressions nag with 1 week of inactivity"

    def handle_bug(self, bug, data):
        if len(bug["regressed_by"]) != 1:
            # either we don't have access to the regressor,
            # or there's more than one, either way leave things alone
            return

        bug_id = str(bug["id"])
        data[bug_id] = {
            "creator": bug["creator"],
            "regressor_id": bug["regressed_by"][0],
            "severity": bug["severity"],
        }

        if "triage_owner_detail" in bug:
            data[bug_id]["triage_owner"] = bug["triage_owner_detail"]

        return bug

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        fields = [
            "id",
            "triage_owner",
            "creator",
            "regressed_by",
            "assigned_to",
            "severity",
        ]

        # Find all bugs with regressed_by information which were open after start_date or
        # whose regressed_by field was set after start_date.
        params = {
            "include_fields": fields,
            "f3": "creation_ts",
            "o3": "greaterthan",
            "v3": "2024-10-01T00:00:00Z",
            "f1": "regressed_by",
            "o1": "isnotempty",
            "f2": "keywords",
            "o2": "allwords",
            "v2": ["regression", "perf-alert"],
            "f9": "days_elapsed",
            "o9": "greaterthan",
            "v9": self.nweeks * 7,
            "status": ["UNCONFIRMED", "NEW", "REOPENED"],
            "resolution": ["---"],
        }

        return params


    def filter_bugs(self, bugs):
        # Exclude bugs whose regressor author is nobody.
        bugs_with_no_authors = []
        for bug in list(bugs.values()):
            if utils.is_no_assignee(bug["regressor_author_email"]):
                logger.warning(
                    "Bug {}, regressor of bug {}, doesn't have an author".format(
                        bug["regressor_id"], bug["id"]
                    )
                )
                bugs_with_no_authors.append(bug["id"])

        # Exclude bugs where the regressor author is inactive or blocked needinfo.
        # TODO: We can drop this when https://github.com/mozilla/bugbot/issues/1465 is implemented.
        # users_info = UserActivity(include_fields=["groups", "requests"]).check_users(
        #     set(bug["regressor_author_email"] for bug in bugs.values()),
        #     keep_active=True,
        #     fetch_employee_info=False,
        # )

        # for bug_id, bug in list(bugs.items()):
        #     user_info = users_info[bug["regressor_author_email"]]
        #     if (
        #         user_info["status"] != UserStatus.ACTIVE
        #         or user_info["requests"]["needinfo"]["blocked"]
        #     ):
        #         bugs_with_no_authors.append(bug_id)

        # TODO: Attempt to needinfo the triage owner instead

        Bugzilla(
            bugids=self.get_list_bugs(bugs),
            comment_include_fields=["creator"],
        ).get_data().wait()

        return bugs

    def get_autofix_change(self):
        pass

    def set_autofix(self, bugs):
        for bugid, info in bugs.items():
            self.extra_ni[bugid] = {
                "regressor_id": str(info["regressor_id"]),
            }
            self.add_auto_ni(
                bugid,
                {
                    "mail": info["regressor_author_email"],
                    "nickname": info["regressor_author_nickname"],
                },
            )

    def get_bugs(self, *args, **kwargs):
        bugs = super(NeedinfoRegressionAuthor, self).get_bugs(*args, **kwargs)
        self.retrieve_regressors(bugs)
        bugs = self.filter_bugs(bugs)
        self.set_autofix(bugs)
        return bugs



if __name__ == "__main__":
    PerfAlertInactiveRegressionNag().run()
