# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner

WHITEBOARD_PAT = re.compile(r"\[access\-s[123]\]")


class SeverityInconsistency(BzCleaner):
    def description(self):
        return "Bugs with inconsistent severity flags"

    def has_needinfo(self):
        return True

    def handle_bug(self, bug, data):
        whiteboard_severities = WHITEBOARD_PAT.findall(bug["whiteboard"])
        assert len(whiteboard_severities) == 1
        whiteboard_severity = whiteboard_severities[0]

        bugid = str(bug["id"])
        data[bugid] = {
            "whiteboard_severity": whiteboard_severity,
            "severity": bug["severity"],
        }
        self.extra_ni = data

        return bug

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "severity", "whiteboard_severity"]

    def get_mail_to_auto_ni(self, bug):
        for field in ["assigned_to", "triage_owner"]:
            person = bug.get(field, "")
            if person and not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None

    def get_bz_params(self, date):
        fields = ["triage_owner", "assigned_to", "severity", "whiteboard"]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "j1": "OR",
            "f1": "OP",
            "f2": "OP",
            "f3": "status_whiteboard",
            "o3": "anywordssubstr",
            "v3": "access-s3",
            "f4": "bug_severity",
            "o4": "anyexact",
            "v4": "S4",
            "f5": "CP",
            "f6": "OP",
            "f7": "status_whiteboard",
            "o7": "anywordssubstr",
            "v7": "access-s1",
            "f8": "bug_severity",
            "o8": "anyexact",
            "v8": "S2,S3,S4",
            "f9": "CP",
            "f10": "OP",
            "f11": "status_whiteboard",
            "o11": "anywordssubstr",
            "v11": "access-s2",
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
