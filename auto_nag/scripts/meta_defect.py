# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class MetaDefect(BzCleaner):
    def __init__(self):
        super(MetaDefect, self).__init__()
        self.nmonths = utils.get_config(self.name(), "months_lookup")

    def description(self):
        return 'Defect with the "meta" keyword with activity for the last {} months'.format(
            self.nmonths
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
            "keywords": "meta",
            "keywords_type": "allwords",
            "bug_type": ["defect"],
            "f1": "days_elapsed",
            "o1": "lessthan",
            "v1": self.nmonths * 30,
        }
        return params


if __name__ == "__main__":
    MetaDefect().run()
