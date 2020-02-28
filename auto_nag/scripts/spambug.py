# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import people
from auto_nag.bugbug_utils import get_bug_ids_classification
from auto_nag.bzcleaner import BzCleaner
from auto_nag.utils import nice_round


class SpamBug(BzCleaner):
    def __init__(self):
        super().__init__()
        self.people = people.People.get_instance()

    def description(self):
        return "[Using ML] Detect spam bugs"

    def columns(self):
        return ["id", "summary", "confidence", "autofixed"]

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
            "v1": "@mozilla",
            "o1": "notsubstring",
            "f2": "reporter",
            "v2": "@softvision",
            "o2": "notsubstring",
            "f3": "creation_ts",
            "o3": "greaterthan",
            "v3": start_date,
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

        results = {}

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
            index = bug_data["index"]

            if prob[1] > self.get_config("confidence_threshold"):
                results[bug_id] = {
                    "id": bug_id,
                    "summary": bug["summary"],
                    "confidence": nice_round(prob[index]),
                    "autofixed": False,
                }

        return results

    def get_autofix_change(self):
        return {}


if __name__ == "__main__":
    SpamBug().run()
