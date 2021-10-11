# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class FuzzingBisectionWithoutRegressedBy(BzCleaner):
    def description(self):
        return "Bugs with a fuzzing bisection and without regressed_by"

    def get_max_ni(self):
        return utils.get_config(self.name(), "max_ni")

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "assigned_to_email": bug["assigned_to"],
            "assigned_to_nickname": bug["assigned_to_detail"]["nick"],
            "depends_on": bug["depends_on"],
        }
        return bug

    def set_autofix(self, bugs):
        for bugid, info in bugs.items():
            self.add_auto_ni(
                bugid,
                {
                    "mail": info["assigned_to_email"],
                    "nickname": info["assigned_to_nickname"],
                },
            )

    def get_bz_params(self, date):
        return {
            "include_fields": ["assigned_to", "depends_on"],
            "f1": "regressed_by",
            "o1": "isempty",
            "n2": 1,
            "f2": "regressed_by",
            "o2": "everchanged",
            "n3": 1,
            "f3": "longdesc",
            "o3": "casesubstring",
            "v3": "since this bug contains a bisection range, could you fill (if possible) the regressed_by field",
            "emaillongdesc1": "1",
            "emailtype1": "exact",
            "email1": "bugmon@mozilla.com",
        }

    def filter_bugs(self, bugs):
        # Exclude bugs assigned to nobody.
        bugs = {
            bug["id"]: bug
            for bug in bugs.values()
            if not utils.is_no_assignee(bug["assigned_to_email"])
        }

        # Exclude bugs that do not have a range found by BugMon.
        def comment_handler(bug, bug_id):
            if not any(
                "BugMon: Reduced build range" in comment["text"]
                or "The bug appears to have been introduced in the following build range"
                in comment["text"]
                for comment in bug["comments"]
            ):
                del bugs[bug_id]

        Bugzilla(
            bugids=self.get_list_bugs(bugs),
            commenthandler=comment_handler,
            comment_include_fields=["text"],
        ).get_data().wait()

        return bugs

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(FuzzingBisectionWithoutRegressedBy, self).get_bugs(
            date=date, bug_ids=bug_ids
        )
        bugs = self.filter_bugs(bugs)
        self.set_autofix(bugs)

        return bugs


if __name__ == "__main__":
    FuzzingBisectionWithoutRegressedBy().run()
