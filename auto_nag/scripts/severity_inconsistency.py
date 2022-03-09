# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class SeverityInconsistency(BzCleaner):

    def description(self):
        return "Bugs with inconsistent severity flags"

    def has_needinfo(self):
        return True

    def handle_bug(self, bug, data):
        self.extra_ni = data

        bugid = str(bug["id"])

        def is_security_flag(flag):
            return flag.startswith("[access-s")

        flags = bug['whiteboard'].split(", ")
        whiteboard_severity = next(filter(is_security_flag, flags), None)

        data[bugid] = {
            "whiteboard_severity": whiteboard_severity,
            "severity": bug["severity"],
        }

        return bug

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "severity", "whiteboard_severity"]

    def get_mail_to_auto_ni(self, bug):
        for f in ["assigned_to", "triage_owner"]:
            person = bug.get(f, "")
            if person and not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f + "_detail"]["nick"]}

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
        }

        return params


if __name__ == "__main__":
    SeverityInconsistency().run()
