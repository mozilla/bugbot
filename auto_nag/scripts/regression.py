# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bugbug_utils import get_bug_ids_classification
from auto_nag.bzcleaner import BzCleaner
from auto_nag.utils import nice_round


class Regression(BzCleaner):
    def __init__(self):
        super().__init__()
        self.autofix_regression = []

    def description(self):
        return "[Using ML] Bugs with missing regression keyword"

    def columns(self):
        return ["id", "summary", "confidence", "autofixed"]

    def sort_columns(self):
        return lambda p: (-p[2], -int(p[0]))

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)

        resolution_skiplist = self.get_config("resolution_skiplist", default=[])
        resolution_skiplist = " ".join(resolution_skiplist)

        reporter_skiplist = self.get_config("reporter_skiplist", default=[])
        reporter_skiplist = ",".join(reporter_skiplist)

        params = {
            "include_fields": ["id", "groups", "summary"],
            "bug_type": "defect",
            "f1": "keywords",
            "o1": "nowords",
            "v1": "regression,feature,meta",
            "f2": "longdesc",
            "o2": "anywordssubstr",
            "v2": "regress caus",
            "f3": "resolution",
            "o3": "nowords",
            "v3": resolution_skiplist,
            "f4": "longdesc",
            "o4": "changedafter",
            "v4": start_date,
            "f5": "longdesc",
            "o5": "changedbefore",
            "v5": end_date,
            "f6": "reporter",
            "o6": "nowords",
            "v6": reporter_skiplist,
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
        bugs = get_bug_ids_classification("regression", bug_ids)

        results = {}

        for bug_id in sorted(bugs.keys()):
            bug_data = bugs[bug_id]

            if not bug_data.get("available", True):
                # The bug was not available, it was either removed or is a
                # security bug
                continue

            if not {"prob"}.issubset(bug_data.keys()):
                raise Exception(f"Invalid bug response {bug_id}: {bug_data!r}")

            bug = raw_bugs[bug_id]
            prob = bug_data["prob"]

            if prob[1] < 0.5:
                continue

            bug_id = str(bug_id)
            results[bug_id] = {
                "id": bug_id,
                "summary": bug["summary"],
                "confidence": nice_round(prob[1]),
                "autofixed": False,
            }

            # Only autofix results for which we are sure enough.
            if prob[1] >= self.get_config("confidence_threshold"):
                results[bug_id]["autofixed"] = True
                self.autofix_regression.append((bug_id, prob[1]))

        return results

    def get_autofix_change(self):
        cc = self.get_config("cc")

        autofix_change = {}
        for bug_id, confidence in self.autofix_regression:
            autofix_change[bug_id] = {
                "keywords": {"add": ["regression"]},
                "cc": {"add": cc},
            }

            if confidence != 1.0:
                autofix_change[bug_id]["comment"] = {
                    "body": "The [Bugbug](https://github.com/mozilla/bugbug/) bot thinks this bug is a regression, but please revert this change in case of error."
                }

        return autofix_change


if __name__ == "__main__":
    Regression().run()
