# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import collections

from libmozdata.bugzilla import Bugzilla

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class RegressionSetStatusFlags(BzCleaner):
    def __init__(self):
        super().__init__()
        self.extra_ni = {}

    def description(self):
        return "Unassigned regressions with non-empty Regressed By field"

    def handle_bug(self, bug, data):
        if len(bug["regressed_by"]) != 1:
            # either we don't have access to the regressor, or there's more than one, either way leave things alone
            return

        data[str(bug["id"])] = {
            "regressor_id": bug["regressed_by"][0],
        }

        return bug

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def set_autofix(self, bugs):
        for bugid, info in bugs.items():
            self.extra_ni[bugid] = {"regressor_id": str(info["regressor_id"])}
            self.add_auto_ni(
                bugid,
                {
                    "mail": info["regressor_author_email"],
                    "nickname": info["regressor_author_nickname"],
                },
            )

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        # Find all bugs with regressed_by information which were open after start_date or
        # whose regressed_by field was set after start_date.

        params = {
            "include_fields": ["id", "regressed_by", "assigned_to"],
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
            for bug in regressor_to_bugs[regressor_bug["id"]]:
                bug["regressor_author_email"] = regressor_bug["assigned_to"]
                bug["regressor_author_nickname"] = regressor_bug["assigned_to_detail"][
                    "nick"
                ]

        Bugzilla(
            bugids={bug["regressor_id"] for bug in bugs.values()},
            bughandler=bug_handler,
            include_fields=["id", "assigned_to"],
        ).get_data().wait()

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        self.retrieve_regressors(bugs)
        self.set_autofix(bugs)
        return bugs


if __name__ == "__main__":
    RegressionSetStatusFlags().run()
