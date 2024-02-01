# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.bugbug_utils import get_bug_ids_classification
from bugbot.bzcleaner import BzCleaner
from bugbot.utils import nice_round


class PerformanceBug(BzCleaner):
    def __init__(self, confidence_threshold=0.9):
        super().__init__()
        self.confidence_threshold = confidence_threshold

    def description(self):
        return "[Using ML] Bugs with Missing Performance Impact"

    def columns(self):
        return ["id", "summary", "confidence", "autofixed"]

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        params = {
            "f1": "creation_ts",
            "o1": "greaterthan",
            "v1": start_date,
            "f2": "keywords",
            "o2": "nowords",
            "v2": "perf,topperf,main-thread-io",
            "f3": "cf_performance_impact",
            "o3": "equals",
            "v3": ["---"],
        }

        return params

    def get_bugs(self, date="today", bug_ids=[]):
        raw_bugs = super().get_bugs(date=date, bug_ids=bug_ids, chunk_size=7000)

        if len(raw_bugs) == 0:
            return {}

        bug_ids = list(raw_bugs.keys())

        bugs = get_bug_ids_classification("performancebug", bug_ids)

        results = {}

        for bug_id, bug_data in bugs.items():
            if not bug_data.get("available", True):
                # The bug was not available, it was either removed or is a
                # security bug
                continue

            bug = raw_bugs[bug_id]
            prob = bug_data["prob"]

            if prob[1] < 0.2:
                continue

            results[bug_id] = {
                "id": bug_id,
                "summary": bug["summary"],
                "confidence": nice_round(prob[1]),
                "autofixed": False,
            }

            # Only autofix results for which we are sure enough.
            if prob[1] >= self.confidence_threshold:
                results[bug_id]["autofixed"] = True

        return results


if __name__ == "__main__":
    PerformanceBug().run()
