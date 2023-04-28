# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class UnderestimatedSeverity(BzCleaner):
    def __init__(self):
        super(UnderestimatedSeverity, self).__init__()
        self.nweeks = self.get_config("weeks_lookup")
        self.ndups = self.get_config("number_dups")
        self.votes = self.get_config("number_votes")
        self.cc = self.get_config("number_cc")
        self.see_also = self.get_config("number_see_also")

        self.extra_ni = {}

    def description(self):
        return "Bugs with underestimated severity for the last {} weeks".format(
            self.nweeks
        )

    def has_needinfo(self):
        return True

    def get_mail_to_auto_ni(self, bug):
        for field in ["assigned_to", "triage_owner"]:
            person = bug.get(field, "")
            if person and not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

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
        ]

    def get_extra_for_template(self):
        return {
            "dups_threshold": self.ndups,
            "votes_threshold": self.votes,
            "cc_threshold": self.cc,
            "see_also_threshold": self.see_also,
        }

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        cc_count = len(bug["cc"])
        dups_count = len(bug["duplicates"])
        votes_count = bug["votes"]
        see_also_count = len(bug["see_also"])

        data[bugid] = {
            "creation": utils.get_human_lag(bug["creation_time"]),
            "last_change": utils.get_human_lag(bug["last_change_time"]),
            "severity": bug["severity"],
            "dups_count": dups_count,
            "votes": votes_count,
            "cc_count": cc_count,
            "see_also_count": see_also_count,
        }

        factors = []
        if dups_count >= self.ndups:
            factors.append(f"{dups_count} duplicates")
        if votes_count >= self.votes:
            factors.append(f"{votes_count} votes")
        if cc_count >= self.cc:
            factors.append(f"{cc_count} CCs")
        if see_also_count >= self.see_also:
            factors.append(f"{see_also_count} See Also bugs")

        self.extra_ni[bugid] = {
            "severity": bug["severity"],
            "factors": utils.english_list(factors),
        }

        return bug

    def get_bz_params(self, date):
        fields = [
            "assigned_to",
            "triage_owner",
            "creation_time",
            "last_change_time",
            "severity",
            "votes",
            "cc",
            "duplicates",
            "see_also",
        ]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "bug_type": "defect",
            "bug_severity": ["S3", "S4"],
            "f1": "keywords",
            "o1": "nowords",
            "v1": ["meta", "intermittent"],
            "f2": "days_elapsed",
            "o2": "lessthan",
            "v2": self.nweeks * 7,
            "j3": "OR",
            "f3": "OP",
            "f4": "dupe_count",
            "o4": "greaterthaneq",
            "v4": self.ndups,
            "f5": "votes",
            "o5": "greaterthaneq",
            "v5": self.votes,
            "f6": "cc_count",
            "o6": "greaterthaneq",
            "v6": self.cc,
            "f7": "see_also_count",
            "o7": "greaterthaneq",
            "v7": self.see_also,
            "f8": "CP",
            "n15": 1,
            "f15": "longdesc",
            "o15": "casesubstring",
            "v15": "could you consider increasing the bug severity?",
        }

        return params


if __name__ == "__main__":
    UnderestimatedSeverity().run()
