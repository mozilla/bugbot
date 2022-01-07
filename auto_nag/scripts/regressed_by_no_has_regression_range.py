# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class Regression(BzCleaner):
    def __init__(self):
        super().__init__()

    def description(self):
        return "Bugs with missing has_regression_range keyword"

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        return {
            "include_fields": ["id", "groups", "summary"],
            "f1": "cf_has_regression_range",
            "o1": "notequals",
            "v1": "yes",
            "f2": "regressed_by",
            "o2": "isnotempty",
        }

    def get_autofix_change(self):
        return {
            "cf_has_regression_range": "yes",
        }


if __name__ == "__main__":
    Regression().run()
