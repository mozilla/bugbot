# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.people import People


class ClosedComment(BzCleaner):
    def __init__(self):
        super().__init__()
        self.people = People.get_instance()

    def description(self):
        return "Closed bugs with a new external comment"

    def handle_bug(self, bug, data):
        last_comment = bug["comments"][-1]
        # Ignore a comment if:
        #   - has any tag (e.g., spam)
        #   - was posted before closing the bug
        #   - was posted by:
        #       - the bug creator
        #       - the bug assignee
        #       - an internal user (e.g., a bot or employee)
        #       - a participant who previously commented on the bug
        if (
            last_comment["tags"]
            or last_comment["creation_time"] <= bug["cf_last_resolved"]
            or last_comment["creator"] in (bug["creator"], bug["assigned_to"])
            or self._internal_user(last_comment["creator"])
            or any(
                last_comment["creator"] == comment["creator"]
                and comment["creation_time"] <= bug["cf_last_resolved"]
                for comment in bug["comments"]
            )
        ):
            return None

        bugid = str(bug["id"])
        data[bugid] = {
            "dupe_of": bug["dupe_of"],
            "is_incomplete": bug["resolution"] == "INCOMPLETE",
        }

        return bug

    def _internal_user(self, email):
        return (
            email.endswith("@mozilla.com")
            or email.endswith("@softvision.com")
            or utils.is_bot_email(email)
            or self.people.is_mozilla(email)
        )

    def get_bugs(self, date="today", bug_ids=..., chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)

        dup_bug_ids = {bug["dupe_of"] for bug in bugs.values() if bug["dupe_of"]}
        dup_bug_is_open = {}
        if dup_bug_ids:
            Bugzilla(
                dup_bug_ids,
                include_fields=["id", "is_open"],
                bughandler=self._handle_dup_bug,
                bugdata=dup_bug_is_open,
            ).wait()

        for bug_id, bug in list(bugs.items()):
            if dup_bug_is_open.get(bug["dupe_of"]):
                dupe_of_id = bug["dupe_of"]
                self.autofix_changes[bug_id] = {
                    "comment": {
                        "body": f"This bug is a duplicate of bug {dupe_of_id}. If you have an input, please comment in bug {dupe_of_id} instead."
                    },
                }
            elif not bug["is_incomplete"]:
                self.autofix_changes[bug_id] = {
                    "comment": {
                        "body": {"body": "This bug is closed. Please file a new bug."}
                    },
                }

        return bugs

    def _handle_dup_bug(self, bug, data):
        data[bug["id"]] = bug["is_open"]

    def ignore_meta(self):
        return True

    def has_access_to_sec_bugs(self):
        return False

    def get_bz_params(self, date):
        fields = [
            "resolution",
            "dupe_of",
            "assigned_to",
            "creator",
            "cf_last_resolved",
            "comments.creator",
            "comments.creation_time",
            "comments.tags",
        ]

        params = {
            "include_fields": fields,
            "bug_type": "defect",
            "bug_status": "__closed__",
            "resolution_type": "notequals",
            "resolution": "WONTFIX",
            "f1": "cf_last_resolved",
            "o1": "lessthan",
            "v1": "-5d",
            "n2": 1,
            "f2": "longdesc",
            "o2": "casesubstring",
            "v2": "Please file a new bug",
            "f3": "longdesc",
            "o3": "changedafter",
            "v3": "-1d",
        }

        return params


if __name__ == "__main__":
    ClosedComment().run()
