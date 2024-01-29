# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.bugbug_utils import get_bug_ids_classification
from bugbot.bzcleaner import BzCleaner
from bugbot.utils import nice_round


class Accessibility(BzCleaner):
    def __init__(self):
        super().__init__()
        self.autofix_bugs = {}

    def description(self):
        return "[Using ML] Detected accessibility bugs"

    def columns(self):
        return ["id", "summary", "confidence", "auto_fixed", "comments"]

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        return {
            "include_fields": ["id", "summary", "comments"],
            "f1": "creation_ts",
            "o1": "greaterthan",
            "v1": start_date,
            "f2": "cf_accessibility_severity",
            "o2": "equals",
            "v2": "---",
            "f3": "keywords",
            "o3": "notsubstring",
            "v3": "access",
        }

    def get_bugs(self, date="today", bug_ids=[]):
        # Retrieve the bugs with the fields defined in get_bz_params
        raw_bugs = super().get_bugs(date=date, bug_ids=bug_ids, chunk_size=7000)

        if len(raw_bugs) == 0:
            return {}

        # Extract the bug ids
        bug_ids = list(raw_bugs.keys())

        # Classify those bugs
        bugs = get_bug_ids_classification("accessibility", bug_ids)

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

            if prob[1] > self.get_config("confidence_threshold"):
                self.autofix_bugs[bug_id] = {
                    "id": bug_id,
                    "summary": bug["summary"],
                    "confidence": nice_round(prob[1]),
                }

        return self.autofix_bugs

    def get_autofix_change(self):
        return {
            bug_id: (
                data.update(
                    {
                        "keywords": {"add": "access"},
                        "comment": {
                            "body": "The [Bugbug](https://github.com/mozilla/bugbug/) bot thinks this bug is an accessibility bug, and is adding the access keyword to the bug. Please correct in case you think the bot is wrong."
                        },
                    }
                )
                or data
            )
            for bug_id, data in self.autofix_bugs.items()
        }


if __name__ == "__main__":
    Accessibility().run()
