# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class LeaveOpen(BzCleaner):
    def __init__(self):
        super(LeaveOpen, self).__init__()

    def description(self):
        return "Closed bugs with leave-open keyword"

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        params = {
            "bug_status": ["RESOLVED", "VERIFIED", "CLOSED"],
            "f1": "keywords",
            "o1": "casesubstring",
            "v1": "leave-open",
            "f2": "resolution",
            "o2": "changedafter",
            "v2": start_date,
            "f3": "resolution",
            "o3": "changedbefore",
            "v3": end_date,
        }

        return params

    def get_autofix_change(self):
        return {"keywords": {"remove": ["leave-open"]}}


if __name__ == "__main__":
    LeaveOpen().run()
