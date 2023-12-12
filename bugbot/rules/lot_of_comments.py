# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class SeveralComments(BzCleaner):
    def __init__(self, nweeks: int = 52, comments: int = 50):
        """Constructor

        Args:
            nweeks: the maximum number of weeks from the submission date
            comments: the number of comments in the bug
        """
        super().__init__()
        self.nweeks = nweeks
        self.comments = comments

    def description(self):
        return "Bugs with several comments for the last {} weeks".format(self.nweeks)

    def has_product_component(self):
        return True

    def columns(self):
        return [
            "id",
            "product",
            "component",
            "summary",
            "creation",
            "last_change",
            "comment_count",
        ]

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        comment_count = bug["comment_count"]

        data[bugid] = {
            "creation": utils.get_human_lag(bug["creation_time"]),
            "last_change": utils.get_human_lag(bug["last_change_time"]),
            "comment_count": comment_count,
        }
        return bug

    def get_bz_params(self, date):
        return {
            "include_fields": ["creation_time", "last_change_time", "comment_count"],
            "resolution": "---",
            "f1": "days_elapsed",
            "o1": "lessthan",
            "v1": self.nweeks * 7,
            "f2": "longdescs.count",
            "o2": "greaterthaneq",
            "v2": self.comments,
            "f3": "keywords",
            "o3": "nowords",
            "v3": ["meta", "intermittent"],
        }


if __name__ == "__main__":
    SeveralComments().run()
