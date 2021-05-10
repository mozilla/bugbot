# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class LeaveOpenSec(BzCleaner):
    def description(self):
        return "Security bugs with leave-open keyword"

    def get_bz_params(self, date):
        start, end = self.get_dates(date)
        bugs = utils.get_bugs_from_pushlog(start, end)
        params = {
            "bug_id": list(bugs),
            "keywords": "leave-open",
            "f1": "bug_group",
            "o1": "substring",
            "v1": "security",
        }
        return params

    def columns(self):
        return ["id"]


if __name__ == "__main__":
    LeaveOpenSec().run()
