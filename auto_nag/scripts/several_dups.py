# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class SeveralDups(BzCleaner):
    def __init__(self):
        super(SeveralDups, self).__init__()
        self.nweeks = utils.get_config(self.name(), "weeks_lookup")
        self.ndups = utils.get_config(self.name(), "number_dups")

    def description(self):
        return 'Bugs with several dups for the last {} weeks'.format(
            self.nweeks
        )

    def columns(self):
        return ["id", "summary", "creation", "last_change"]

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "creation": utils.get_human_lag(bug["creation_time"]),
            "last_change": utils.get_human_lag(bug["last_change_time"]),
        }
        return bug

    def get_bz_params(self, date):
        params = {
            "include_fields": ["creation_time", "last_change_time"],
            "resolution": "---",
            "f1": "days_elapsed",
            "o1": "lessthan",
            "v1": self.nweeks * 7,
            "f2": "dupe_count",
            "o2": "greaterthaneq",
            "v2": self.ndups,
        }
        return params


if __name__ == "__main__":
    SeveralDups().run()
