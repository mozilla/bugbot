# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class TopcrashBadSeverity(BzCleaner):
    def __init__(self):
        super(TopcrashBadSeverity, self).__init__()
        self.extra_ni = {}

    def description(self):
        return "Bugs with topcrash keyword but incorrect severity"

    def ignore_date(self):
        return True

    def ignore_meta(self):
        return True

    def get_mail_to_auto_ni(self, bug):
        for field in ["assigned_to", "triage_owner"]:
            person = bug.get(field, "")
            if not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        self.extra_ni[bugid] = {
            "severity": bug["severity"],
        }
        return bug

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def get_bz_params(self, date):
        fields = [
            "triage_owner",
            "assigned_to",
            "severity",
        ]

        return {
            "include_fields": fields,
            "resolution": ["---"],
            "bug_severity": [
                "S3",
                "normal",
                "S4",
                "minor",
                "trivial",
                "enhancement",
            ],
            "keywords": ["topcrash", "topcrash-startup"],
            "n1": 1,
            "f1": "longdesc",
            "o1": "casesubstring",
            "v1": "could you consider increasing the severity of this top-crash bug?",
        }


if __name__ == "__main__":
    TopcrashBadSeverity().run()
