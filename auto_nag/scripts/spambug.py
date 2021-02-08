# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import people
from auto_nag.bugbug_utils import get_bug_ids_classification
from auto_nag.bzcleaner import BzCleaner
from auto_nag.utils import nice_round

COMMENT = """
The [Bugbug](https://github.com/mozilla/bugbug/) bot thinks this bug is invalid.
If you think the bot is wrong, please reopen the bug and move it back to its prior component.

Be aware this is a production bug database used by the Mozilla community to develop Firefox, and other products.
Filing test bugs here wastes the time of all our contributors, volunteers, as well as paid employees.
If you continue to abuse bugzilla.mozilla.org your account will be disabled.
""".strip()


class SpamBug(BzCleaner):
    def __init__(self):
        super().__init__()
        self.autofix_bugs = {}
        self.people = people.People.get_instance()

    def description(self):
        return "[Using ML] Detect spam bugs"

    def columns(self):
        return ["id", "summary", "confidence"]

    def sort_columns(self):
        return lambda p: (-p[2], -int(p[0]))

    def handle_bug(self, bug, data):
        reporter = bug["creator"]
        if self.people.is_mozilla(reporter):
            return None

        return bug

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        return {
            "include_fields": ["id", "groups", "summary", "creator"],
            # Ignore closed bugs.
            "bug_status": "__open__",
            "f1": "reporter",
            "v1": "%group.editbugs%",
            "o1": "notsubstring",
            "f2": "creation_ts",
            "o2": "greaterthan",
            "v2": start_date,
        }

    def get_bugs(self, date="today", bug_ids=[]):
        # Retrieve the bugs with the fields defined in get_bz_params
        raw_bugs = super().get_bugs(date=date, bug_ids=bug_ids, chunk_size=7000)

        if len(raw_bugs) == 0:
            return {}

        # Extract the bug ids
        bug_ids = list(raw_bugs.keys())

        # Classify those bugs
        bugs = get_bug_ids_classification("spambug", bug_ids)

        for bug_id in sorted(bugs.keys()):
            bug_data = bugs[bug_id]

            if not bug_data.get("available", True):
                # The bug was not available, it was either removed or is a
                # security bug
                continue

            if not {"prob", "index"}.issubset(bug_data.keys()):
                raise Exception(f"Invalid bug response {bug_id}: {bug_data!r}")

            bug = raw_bugs[bug_id]
            prob = bug_data["prob"]

            if prob[1] < self.get_config("confidence_threshold"):
                continue

            self.autofix_bugs[bug_id] = {
                "id": bug_id,
                "summary": bug["summary"],
                "confidence": nice_round(prob[1]),
            }

        return self.autofix_bugs

    def get_autofix_change(self):
        result = {}
        for bug_id in self.autofix_bugs:
            result[bug_id] = {
                "comment": {
                    "body": COMMENT.format(self.autofix_bugs[bug_id]["confidence"])
                },
                "product": "Invalid Bugs",
                "component": "General",
                "version": "unspecified",
                "milestone": "---",
                "status": "RESOLVED",
                "resolution": "INVALID",
            }
        return result


if __name__ == "__main__":
    SpamBug().run()
