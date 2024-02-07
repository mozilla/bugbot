# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class BugScore(BzCleaner):
    def __init__(self):
        super(BugScore, self).__init__()
        self.ndups = self.get_config("number_dups")
        self.votes = self.get_config("number_votes")
        self.cc = self.get_config("number_cc")
        self.see_also = self.get_config("number_see_also")
        self.comments = self.get_config("number_comments")

        # Weights for each category
        self.votes_weight = 0.5
        self.see_also_weight = 0.8
        self.dups_weight = 1.0
        self.comments_weight = 0.4
        self.ccs_weight = 0.3
        self.threshold = 20

        self.extra_ni = {}

    def description(self):
        return "Bugs scores"

    def sort_columns(self):
        return lambda p: (-p[9], -int(p[0]))

    def columns(self):
        return [
            "id",
            "summary",
            "creation",
            "last_change",
            "severity",
            "dups_count",
            "votes",
            "cc_count",
            "see_also_count",
            "user_impact_score",
            "comment_count",
            "product",
            "component",
            "type",
        ]

    def get_extra_for_template(self):
        return {
            "dups_threshold": self.ndups,
            "votes_threshold": self.votes,
            "cc_threshold": self.cc,
            "see_also_threshold": self.see_also,
            "comments_threshold": self.comments,
            "votes_weight": self.votes_weight,
            "see_also_weight": self.see_also_weight,
            "dups_weight": self.dups_weight,
            "comments_weight": self.comments_weight,
            "ccs_weight": self.ccs_weight,
            "threshold": self.threshold,
        }

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        cc_count = len(bug["cc"])
        dups_count = len(bug["duplicates"])
        votes_count = bug["votes"]
        see_also_count = len(bug["see_also"])
        comment_count = bug["comment_count"]

        # Calculating the User Impact Score
        user_impact_score = round(
            (votes_count * self.votes_weight)
            + (see_also_count * self.see_also_weight)
            + (dups_count * self.dups_weight)
            + (comment_count * self.comments_weight)
            + (cc_count * self.ccs_weight)
        )
        if user_impact_score < self.threshold:
            return
        data[bugid] = {
            "creation": utils.get_human_lag(bug["creation_time"]),
            "last_change": utils.get_human_lag(bug["last_change_time"]),
            "severity": bug["severity"],
            "dups_count": dups_count,
            "votes": votes_count,
            "cc_count": cc_count,
            "see_also_count": see_also_count,
            "user_impact_score": user_impact_score,
            "comment_count": comment_count,
            "product": bug["product"],
            "component": bug["component"],
            "type": bug["type"],
        }

        return bug

    def get_bz_params(self, date):
        fields = [
            "creation_time",
            "last_change_time",
            "severity",
            "votes",
            "cc",
            "duplicates",
            "see_also",
            "comment_count",
            "product",
            "component",
            "type",
        ]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "keywords",
            "o1": "nowords",
            "v1": ["meta", "intermittent"],
            "j3": "OR",
            "f3": "OP",
            "f4": "dupe_count",
            "o4": "greaterthaneq",
            "v4": "5",
            "f5": "votes",
            "o5": "greaterthaneq",
            "v5": "10",
            "f6": "cc_count",
            "o6": "greaterthaneq",
            "v6": "20",
            "f7": "see_also_count",
            "o7": "greaterthaneq",
            "v7": "2",
            "f8": "CP",
        }

        return params


if __name__ == "__main__":
    BugScore().run()
