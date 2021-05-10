# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class TopcrashBadSeverity(BzCleaner):
    def description(self):
        return "Bugs with topcrash keyword but incorrect severity"

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        return {
            "resolution": ["---"],
            "bug_severity": ["major", "normal", "minor", "trivial", "enhancement"],
            "keywords": "topcrash",
            "keywords_type": "allwords",
        }


if __name__ == "__main__":
    TopcrashBadSeverity().run()
