# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.severity import Severity


class SeverityHigherDuplicates(BzCleaner):
    def __init__(self):
        super().__init__()
        self.extra_ni = None

    def description(self):
        return "Bugs with duplicates that have higher severity"

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "severity": Severity(bug["severity"]),
            "duplicates": bug["duplicates"],
        }

        return bug

    def get_bugs(self, date="today", bug_ids=..., chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)

        dup_bug_ids = {bug_id for bug in bugs.values() for bug_id in bug["duplicates"]}
        dup_bugs = {}

        Bugzilla(
            dup_bug_ids,
            include_fields=["id", "severity", "cf_last_resolved"],
            bughandler=self._handle_dup_bug,
            bugdata=dup_bugs,
        ).wait()

        # Keep only bugs that have duplicates with higher severity than them
        for bug_id, bug in list(bugs.items()):
            higher_severity_dups = [
                dup_bugs[dup_id]
                for dup_id in bug["duplicates"]
                if dup_id in dup_bugs and dup_bugs[dup_id]["severity"] > bug["severity"]
            ]

            if higher_severity_dups:
                bug["duplicates"] = higher_severity_dups
            else:
                del bugs[bug_id]

        # Exclude duplicate bugs that were linked before downgrading the severity
        Bugzilla(
            bugs.keys(),
            include_fields=["id", "triage_owner", "assigned_to", "history"],
            bughandler=self._handle_final_bug_filtering,
            bugdata=bugs,
        ).wait()

        self.extra_ni = bugs

        return bugs

    def _handle_dup_bug(self, bug, data):
        if bug["severity"] not in Severity.ACCEPTED_VALUES:
            return

        bug["severity"] = Severity(bug["severity"])
        data[bug["id"]] = bug

    def _get_last_severity_downgrade_time(self, bug):
        for entry in reversed(bug["history"]):
            for change in entry["changes"]:
                if (
                    change["field_name"] == "severity"
                    and change["added"] in Severity.SEVERITY_LEVELS
                    and change["removed"] in Severity.SEVERITY_LEVELS
                    and Severity(change["added"]) < Severity(change["removed"])
                ):
                    return entry["when"]
        return None

    def _handle_final_bug_filtering(self, bug, data):
        bugid = str(bug["id"])
        duplicates = data[bugid]["duplicates"]
        downgrade_time = self._get_last_severity_downgrade_time(bug)
        if downgrade_time:
            duplicates = [
                dup_bug
                for dup_bug in duplicates
                # cf_last_resolved reflects when it was linked as a duplicate
                if dup_bug["cf_last_resolved"] > downgrade_time
            ]

        if duplicates and self.add_auto_ni(bugid, utils.get_mail_to_ni(bug)):
            data[bugid]["duplicates"] = duplicates
            data[bugid]["suggested_severity"] = max(
                dup_bug["severity"] for dup_bug in duplicates
            )
        else:
            del data[bugid]

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "severity", "suggested_severity"]

    def get_bz_params(self, date):
        fields = ["severity", "duplicates"]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "bug_severity",
            "o1": "anyexact",
            "v1": "S2,S3,S4,S5",
            "f2": "bug_type",
            "o2": "equals",
            "v2": "defect",
            "f3": "duplicates",
            "o3": "isnotempty",
            "n4": 1,
            "f4": "longdesc",
            "o4": "casesubstring",
            "v4": "could you consider increasing the severity of this bug to",
        }

        return params


if __name__ == "__main__":
    SeverityHigherDuplicates().run()
