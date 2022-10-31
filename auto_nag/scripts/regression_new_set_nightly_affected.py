# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class RegressionNewSetNightlyAffected(BzCleaner):
    """Set nightly status to affected on newly filed regressions"""

    def __init__(self):
        super().__init__()
        if not self.init_versions():
            return

    def description(self):
        return "Set nightly status to affected on newly filed regressions"

    def get_bz_params(self, date):
        return {
            "resolution": ["---", "FIXED"],
            "bug_status_type": "notequals",
            "bug_status": "UNCONFIRMED",
            "keywords": "regression",
            "f1": "creation_ts",
            "o1": "greaterthan",
            "v1": "-7d",
            "f2": "creation_ts",
            "o2": "lessthan",
            "v2": "-2d",
            "f3": "regressed_by",
            "o3": "isempty",
            "f4": "cf_status_firefox_nightly",
            "o4": "equals",
            "v4": "---",
            "f5": "cf_status_firefox_beta",
            "o5": "equals",
            "v5": "---",
            "f6": "cf_status_firefox_release",
            "o6": "equals",
            "v6": "---",
        }

    def get_autofix_change(self):
        nightly_status_flag = utils.get_flag(
            self.versions["nightly"], "status", "nightly"
        )
        return {
            "comment": {
                "body": "This bug has been marked as a regression. Setting status flag for Nightly to `affected`."
            },
            nightly_status_flag: "affected",
        }


if __name__ == "__main__":
    RegressionNewSetNightlyAffected().run()
