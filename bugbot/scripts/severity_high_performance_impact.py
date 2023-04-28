# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.constants import LOW_SEVERITY


class SeverityHighPerformanceImpact(BzCleaner):
    def description(self):
        return "Bugs with high performance impact which are set to low severity"

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "severity": bug["severity"],
        }

        return bug

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)
        self.extra_ni = bugs

        return bugs

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "severity"]

    def get_mail_to_auto_ni(self, bug):
        return utils.get_mail_to_ni(bug)

    def get_bz_params(self, date):
        fields = ["triage_owner", "assigned_to", "severity", "keywords"]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "bug_severity": LOW_SEVERITY,
            "cf_performance_impact": "high",
            "n1": 1,
            "f1": "longdesc",
            "o1": "casesubstring",
            "v1": "could you consider increasing the severity of this performance-impacting bug?",
        }

        return params


if __name__ == "__main__":
    SeverityHighPerformanceImpact().run()
