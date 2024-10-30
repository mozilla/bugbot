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
        self.nweeks = 1

    def description(self):
        return "PerfAlert regressions nag with 1 week of inactivity"

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
            "v9": 1,
            "status": ["UNCONFIRMED", "NEW", "REOPENED"],
            "resolution": ["---"],
        }

        return params


    def get_bugs(self, *args, **kwargs):
        bugs = super(NeedinfoRegressionAuthor, self).get_bugs(*args, **kwargs)
        print("ssparky retrieving regressors")
        self.retrieve_regressors(bugs)
        print("sparkyyyyyy filtering bugs")
        bugs = self.filter_bugs(bugs)
        print(bugs)

        # self.set_autofix(bugs)
        return bugs



if __name__ == "__main__":
    PerfAlertInactiveRegressionNag().run()
