# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class SeveralVotes(BzCleaner):
    def __init__(self):
        super(SeveralVotes, self).__init__()
        self.nweeks = utils.get_config(self.name(), "weeks_lookup")
        self.votes = utils.get_config(self.name(), "number_votes")

    def description(self):
        return "Bugs with several votes for the last {} weeks".format(self.nweeks)

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
            "votes_type": "greaterthaneq",
            "votes": "10",
            "f2": "votes",
            "f3": "keywords",
            "o3": "nowords",
            "v3": ["meta", "intermittent"],
        }
        return params


if __name__ == "__main__":
    SeveralVotes().run()
