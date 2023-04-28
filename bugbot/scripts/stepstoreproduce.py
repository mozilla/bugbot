# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.bugbug_utils import get_bug_ids_classification
from bugbot.bzcleaner import BzCleaner
from bugbot.utils import nice_round


class StepsToReproduce(BzCleaner):
    def description(self):
        return "[Using ML] Bugs with missing steps to reproduce"

    def columns(self):
        return ["id", "summary", "has_str", "confidence", "autofixed"]

    def sort_columns(self):
        return lambda p: (-p[3], -int(p[0]))

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)

        params = {
            "include_fields": ["id", "groups", "summary"],
            "bug_type": "defect",
            "f1": "longdesc",
            "o1": "changedafter",
            "v1": start_date,
            "f2": "longdesc",
            "o2": "changedbefore",
            "v2": end_date,
            "f3": "reporter",
            "o3": "notsubstring",
            "v3": "%group.editbugs%",
            "f4": "cf_has_str",
            "o4": "equals",
            "v4": "---",
            "n5": 1,
            "f5": "cf_has_str",
            "o5": "changedafter",
            "v5": "1970-01-01",
            "f6": "keywords",
            "o6": "nowords",
            "v6": "intermittent-failure",
            # Ignore closed bugs.
            "bug_status": "__open__",
        }

        return params

    def get_bugs(self, date="today", bug_ids=[]):
        # Retrieve the bugs with the fields defined in get_bz_params
        raw_bugs = super().get_bugs(date=date, bug_ids=bug_ids, chunk_size=7000)

        if len(raw_bugs) == 0:
            return {}

        # Extract the bug ids
        bug_ids = list(raw_bugs.keys())

        # Classify those bugs
        bugs = get_bug_ids_classification("stepstoreproduce", bug_ids)

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

            results[bug_id] = {
                "id": bug_id,
                "summary": bug["summary"],
                "has_str": "yes" if prob[1] > 0.5 else "no",
                "confidence": nice_round(prob[index]),
                "autofixed": False,
            }

        return results

    def get_autofix_change(self):
        return {}


if __name__ == "__main__":
    StepsToReproduce().run()
