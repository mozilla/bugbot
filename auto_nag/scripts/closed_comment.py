# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

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
        if (
            last_comment["creation_time"] <= bug["cf_last_resolved"]
            or last_comment["creator"] in (bug["creator"], bug["assigned_to"])
            or self._internal_user(last_comment["creator"])
            or any(
                last_comment["creator"] == comment["creator"]
                and comment["creation_time"] < bug["cf_last_resolved"]
                for comment in bug["comments"]
            )
        ):
            return None

        return bug

    def _internal_user(self, email):
        return (
            email.endswith("@mozilla.com")
            or email.endswith("@softvision.com")
            or utils.is_bot_email(email)
            or self.people.is_mozilla(email)
        )

    def get_bz_params(self, date):
        fields = [
            "assigned_to",
            "creator",
            "cf_last_resolved",
            "comments.creator",
            "comments.creation_time",
        ]

        params = {
            "include_fields": fields,
            "bug_type": "defect",
            "bug_status": "__closed__",
            "f1": "cf_last_resolved",
            "o1": "greaterthan",
            "v1": "-5d",
            "n2": 1,
            "f2": "longdesc",
            "o2": "casesubstring",
            "v2": "Please file a new bug",
        }

        return params

    def get_autofix_change(self):
        return {
            "comment": {"body": "This bug is closed. Please file a new bug."},
        }


if __name__ == "__main__":
    ClosedComment().run()
