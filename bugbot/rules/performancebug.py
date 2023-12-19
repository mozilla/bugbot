# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.bugbug_utils import get_bug_ids_classification
from bugbot.bzcleaner import BzCleaner
from bugbot.utils import nice_round


class PerformanceBug(BzCleaner):
    def description(self):
        return "[Using ML] Detect potential performance-related bugs"

    def columns(self):
        return ["id", "summary", "confidence"]

    def sort_columns(self):
        return lambda p: (-p[3], -int(p[0]))

    def get_bz_params(self, date):
        params = {
            "include_fields": ["id", "summary", "whiteboard"],
            "f1": "keywords",
            "o1": "anywords",
            "v1": "perf,topperf,main-thread-io",
            "f2": "status_whiteboard",
            "o2": "anywords",
            "v2": "[fxperf,[fxperfsize,[snappy,[pdfjs-c-performance,[pdfjs-performance,[sp3",
            "f3": "cf_performance_impact",
            "o3": "notequals",
            "v3": ["---", "?"],
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
        bugs = get_bug_ids_classification("performancebug", bug_ids)

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
                "confidence": nice_round(prob[index]),
            }

        return results

    def get_autofix_change(self):
        return {}


if __name__ == "__main__":
    PerformanceBug().run()
