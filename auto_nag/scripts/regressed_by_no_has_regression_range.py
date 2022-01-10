# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class Regression(BzCleaner):
    def __init__(self):
        super().__init__()

    def description(self):
        return "Bugs with missing has_regression_range keyword"

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        return {
            "include_fields": ["id", "groups", "summary"],
            "f1": "cf_has_regression_range",
            "o1": "notequals",
            "v1": "yes",
            "f2": "regressed_by",
            "o2": "isnotempty",
            "f3": "creation_ts",
            "o3": "greaterthan",
            "v3": start_date,
        }

    def get_autofix_change(self):
        return {
            "cf_has_regression_range": "yes",
        }


if __name__ == "__main__":
    Regression().run()
