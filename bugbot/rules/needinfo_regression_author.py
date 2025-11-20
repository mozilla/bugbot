# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import collections

from libmozdata.bugzilla import Bugzilla

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.user_activity import UserActivity, UserStatus


class NeedinfoRegressionAuthor(BzCleaner):
    def __init__(self):
        super().__init__()
        self.extra_ni = {}
        self.private_regressor_ids: set[str] = set()

    def description(self):
        return "Unassigned regressions with non-empty Regressed By field"

    def handle_bug(self, bug, data):
        if not bug["regressed_by"]:
            return

        data[str(bug["id"])] = {
            "creator": bug["creator"],
            "regressor_id": max(bug["regressed_by"]),
            "severity": bug["severity"],
        }

        return bug

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def get_autofix_change(self):
        return {
            "keywords": {"add": ["regression"]},
        }

    def set_autofix(self, bugs):
        for bugid, info in bugs.items():
            self.extra_ni[bugid] = {
                "regressor_id": str(info["regressor_id"]),
                "suggest_set_severity": info["suggest_set_severity"],
            }
            self.add_auto_ni(
                bugid,
                {
                    "mail": info["regressor_author_email"],
                    "nickname": info["regressor_author_nickname"],
                },
            )

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        fields = [
            "id",
            "creator",
            "regressed_by",
            "assigned_to",
            "severity",
        ]

        # Find all bugs with regressed_by information which were open after start_date or
        # whose regressed_by field was set after start_date.
        params = {
            "include_fields": fields,
            "f1": "OP",
            "j1": "OR",
            "f2": "creation_ts",
            "o2": "greaterthan",
            "v2": start_date,
            "f3": "regressed_by",
            "o3": "changedafter",
            "v3": start_date,
            "f4": "CP",
            "f5": "regressed_by",
            "o5": "isnotempty",
            "n6": 1,
            "f6": "longdesc",
            "o6": "casesubstring",
            "v6": "since you are the author of the regressor",
            "f7": "flagtypes.name",
            "o7": "notsubstring",
            "v7": "needinfo?",
            "status": ["UNCONFIRMED", "NEW", "REOPENED"],
            "resolution": ["---"],
        }

        utils.get_empty_assignees(params)

        return params

    def retrieve_regressors(self, bugs):
        regressor_to_bugs = collections.defaultdict(list)
        for bug in bugs.values():
            regressor_to_bugs[bug["regressor_id"]].append(bug)

        def bug_handler(regressor_bug):
            if regressor_bug.get("groups"):
                regressor_bug_id = str(regressor_bug["id"])
                self.private_regressor_ids.add(regressor_bug_id)

            for bug in regressor_to_bugs[regressor_bug["id"]]:
                bug["regressor_author_email"] = regressor_bug["assigned_to"]
                bug["regressor_author_nickname"] = regressor_bug["assigned_to_detail"][
                    "nick"
                ]

        Bugzilla(
            bugids={bug["regressor_id"] for bug in bugs.values()},
            bughandler=bug_handler,
            include_fields=["id", "assigned_to", "groups"],
        ).get_data().wait()

    def filter_bugs(self, bugs):
        # Exclude bugs whose regressor author is nobody.
        for bug in list(bugs.values()):
            if utils.is_no_assignee(bug["regressor_author_email"]):
                logger.warning(
                    "Bug {}, regressor of bug {}, doesn't have an author".format(
                        bug["regressor_id"], bug["id"]
                    )
                )
                del bugs[bug["id"]]

        # Exclude bugs whose creator is the regressor author.
        bugs = {
            bug["id"]: bug
            for bug in bugs.values()
            if bug["creator"] != bug["regressor_author_email"]
        }

        # Exclude bugs where a commentor is the regressor author.
        def comment_handler(bug, bug_id):
            if any(
                comment["creator"] == bugs[bug_id]["regressor_author_email"]
                for comment in bug["comments"]
            ):
                del bugs[str(bug_id)]

        # Exclude bugs where the regressor author is inactive or blocked needinfo.
        # TODO: We can drop this when https://github.com/mozilla/bugbot/issues/1465 is implemented.
        users_info = UserActivity(include_fields=["groups", "requests"]).check_users(
            set(bug["regressor_author_email"] for bug in bugs.values()),
            keep_active=True,
            fetch_employee_info=True,
        )

        for bug_id, bug in list(bugs.items()):
            user_info = users_info[bug["regressor_author_email"]]
            if (
                user_info["status"] != UserStatus.ACTIVE
                or user_info["requests"]["needinfo"]["blocked"]
            ):
                del bugs[bug_id]
            else:
                bug["suggest_set_severity"] = bug["severity"] in (
                    "--",
                    "n/a",
                ) and user_info.get("is_employee")

        Bugzilla(
            bugids=self.get_list_bugs(bugs),
            commenthandler=comment_handler,
            comment_include_fields=["creator"],
        ).get_data().wait()

        return bugs

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        self.retrieve_regressors(bugs)
        bugs = self.filter_bugs(bugs)
        self.set_autofix(bugs)
        return bugs

    def set_needinfo(self):
        res = super().set_needinfo()
        for bug_id, needinfo_action in res.items():
            needinfo_action["comment"]["is_private"] = (
                bug_id in self.private_regressor_ids
            )

        return res


if __name__ == "__main__":
    NeedinfoRegressionAuthor().run()
