# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class SeveralSeeAlso(BzCleaner):
    def __init__(self, nweeks: int = 52, min_see_also: int = 5):
        """Constructor

        Args:
            nweeks: the maximum number of weeks from the submission date
            min_see_also: the minimum number of 'see also' in the bug
        """
        super().__init__()
        self.nweeks = nweeks
        self.see_also = see_also

    def description(self):
        return "Bugs with several see_also for the last {} weeks".format(self.nweeks)

    def columns(self):
        return ["id", "summary", "creation", "last_change", "see_also_count"]

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        see_also_count = len(bug["see_also"])

        data[bugid] = {
            "creation": utils.get_human_lag(bug["creation_time"]),
            "last_change": utils.get_human_lag(bug["last_change_time"]),
            "see_also_count": see_also_count,
        }
        return bug

    def get_bz_params(self, date):
        return {
            "include_fields": ["creation_time", "last_change_time", "see_also"],
            "resolution": "---",
            "f1": "days_elapsed",
            "o1": "lessthan",
            "v1": self.nweeks * 7,
            "f2": "see_also_count",
            "o2": "greaterthaneq",
            "v2": self.see_also,
            "f3": "keywords",
            "o3": "nowords",
            "v3": ["meta", "intermittent"],
        }


if __name__ == "__main__":
    SeveralSeeAlso().run()
