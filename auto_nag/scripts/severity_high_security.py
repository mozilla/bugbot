# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner

HIGH_SECURITY_KEYWORDS = ["sec-high", "sec-critical"]


class SeverityHighSecurity(BzCleaner):
    def description(self):
        return "Bugs with high security keywords which are set to low severity"

    def has_needinfo(self):
        return True

    def handle_bug(self, bug, data):
        security_keywords = [
            keyword for keyword in bug["keywords"] if keyword in HIGH_SECURITY_KEYWORDS
        ]
        assert len(security_keywords) == 1
        security_keyword = security_keywords[0]

        bugid = str(bug["id"])
        data[bugid] = {
            "security_keyword": security_keyword,
            "severity": bug["severity"],
        }
        self.extra_ni = data

        return bug

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "severity", "security_keyword"]

    def get_mail_to_auto_ni(self, bug):
        for field in ["assigned_to", "triage_owner"]:
            person = bug.get(field, "")
            if person and not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None

    def get_bz_params(self, date):
        fields = ["triage_owner", "assigned_to", "severity", "keywords"]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "f3": "keywords",
            "o3": "anyexact",
            "v3": HIGH_SECURITY_KEYWORDS,
            "f4": "bug_severity",
            "o4": "anyexact",
            "v4": ["S3", "S4"],
            "n15": 1,
            "f15": "longdesc",
            "o15": "casesubstring",
            "v15": "could you consider increasing the severity of this security bug?",
        }

        return params


if __name__ == "__main__":
    SeverityHighSecurity().run()
