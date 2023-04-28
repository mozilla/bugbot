# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class WarnRegressedBy(BzCleaner):
    def __init__(self):
        super(WarnRegressedBy, self).__init__()
        self.regressions = {}
        self.threshold = self.get_config("threshold", 3)
        self.days = self.get_config("days_lookup", 14)
        self.step = 0

    def description(self):
        return "Bugs with more than {} regressions reported in the last {} days".format(
            self.threshold, self.days
        )

    def get_extra_for_template(self):
        return {"threshold": self.threshold, "days": self.days}

    def has_product_component(self):
        return self.step != 0

    def has_assignee(self):
        return self.step != 0

    def has_last_comment_time(self):
        return self.step != 0

    def columns(self):
        return [
            "id",
            "summary",
            "product",
            "component",
            "creation",
            "priority",
            "severity",
            "assignee",
            "last_comment",
        ]

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        if self.step == 0:
            for reg_id in bug["regressed_by"]:
                reg_id = str(reg_id)
                if reg_id not in self.regressions:
                    self.regressions[reg_id] = [bugid]
                else:
                    self.regressions[reg_id].append(bugid)
        else:
            data[bugid] = {
                "creation": utils.get_human_lag(bug["creation_time"]),
                "priority": bug["priority"],
                "severity": bug["severity"],
            }

        return bug

    def to_warn(self):
        self.bugs_to_warn = []
        for reg_id, bids in self.regressions.items():
            if len(bids) >= self.threshold:
                self.bugs_to_warn.append(reg_id)

    def get_bz_params(self, date):
        if self.step == 0:
            start_date, _ = self.get_dates(date)
            fields = ["regressed_by"]
            params = {
                "include_fields": fields,
                "f1": "regressed_by",
                "o1": "isnotempty",
                "f2": "creation_ts",
                "o2": "greaterthan",
                "v2": start_date,
            }
        else:
            fields = ["creation_time", "priority", "severity"]
            params = {"include_fields": fields}

        return params

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(WarnRegressedBy, self).get_bugs(date=date, bug_ids=bug_ids)
        self.to_warn()
        if self.bugs_to_warn:
            self.step = 1
            bugs = super(WarnRegressedBy, self).get_bugs(
                date=date, bug_ids=self.bugs_to_warn
            )
            return bugs

        return {}


if __name__ == "__main__":
    WarnRegressedBy().run()
