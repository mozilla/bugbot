# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner

# TODO: should be moved when resolving https://github.com/mozilla/relman-auto-nag/issues/1384
LOW_SEVERITY = ["S3", "normal", "S4", "minor", "trivial", "enhancement"]


class SeverityHighCompatPriority(BzCleaner):
    def description(self):
        return "Bugs with P1 WebCompat priority and severity set to low"

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "severity": bug["severity"],
        }
        self.extra_ni = data

        return bug

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "severity"]

    def get_mail_to_auto_ni(self, bug):
        for field in ["assigned_to", "triage_owner"]:
            person = bug.get(field, "")
            if person and not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None

    def get_bz_params(self, date):
        fields = ["triage_owner", "assigned_to", "severity"]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "cf_webcompat_priority": "P1",
            "bug_severity": LOW_SEVERITY,
            "n1": 1,
            "f1": "longdesc",
            "o1": "casesubstring",
            "v1": "could you consider increasing the severity of this web compatibility bug?",
        }

        return params


if __name__ == "__main__":
    SeverityHighCompatPriority().run()
