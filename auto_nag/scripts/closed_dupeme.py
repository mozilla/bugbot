# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class DupeMe(BzCleaner):
    def description(self):
        return "Closed bugs with dupeme keyword"

    def get_bz_params(self, date):
        days_lookup = self.get_config("days_lookup", default=180)
        params = {
            "bug_status": ["RESOLVED", "VERIFIED", "CLOSED"],
            "f1": "keywords",
            "o1": "casesubstring",
            "v1": "dupeme",
            "f2": "days_elapsed",
            "o2": "lessthan",
            "v2": days_lookup,
        }

        return params

    def get_autofix_change(self):
        return {"keywords": {"remove": ["dupeme"]}}


if __name__ == "__main__":
    DupeMe().run()
