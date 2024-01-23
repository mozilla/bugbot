# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class SeverityInconsistency(BzCleaner):
    def description(self):
        return "Bugs with inconsistent severity flags"

    def has_needinfo(self):
        return True

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "accessibility_severity": bug["cf_accessibility_severity"],
            "severity": bug["severity"],
        }
        self.extra_ni = data

        return bug

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "severity", "accessibility_severity"]

    def get_mail_to_auto_ni(self, bug):
        for field in ["triage_owner", "assigned_to"]:
            person = bug.get(field, "")
            if person and not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None

    def get_bz_params(self, date):
        fields = [
            "triage_owner",
            "assigned_to",
            "severity",
            "cf_accessibility_severity",
        ]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "j1": "OR",
            "f1": "OP",
            "f2": "OP",
            "f3": "cf_accessibility_severity",
            "o3": "equals",
            "v3": "s3",
            "f4": "bug_severity",
            "o4": "equals",
            "v4": "S4",
            "f5": "CP",
            "f6": "OP",
            "f7": "cf_accessibility_severity",
            "o7": "equals",
            "v7": "s1",
            "f8": "bug_severity",
            "o8": "anyexact",
            "v8": "S2,S3,S4",
            "f9": "CP",
            "f10": "OP",
            "f11": "cf_accessibility_severity",
            "o11": "equals",
            "v11": "s2",
            "f12": "bug_severity",
            "o12": "anyexact",
            "v12": "S3,S4",
            "f13": "CP",
            "f14": "CP",
            "n15": 1,
            "f15": "longdesc",
            "o15": "casesubstring",
            "v15": "could you consider increasing the severity?",
        }

        return params


if __name__ == "__main__":
    SeverityInconsistency().run()
