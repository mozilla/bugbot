# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.bugbug_utils import get_bug_ids_classification
from bugbot.bzcleaner import BzCleaner
from bugbot.utils import nice_round


class DefectEnhancementTask(BzCleaner):
    def __init__(self):
        super().__init__()
        self.autofix_type = {}

    def description(self):
        return "[Using ML] Check that the bug type is the same as predicted by bugbug"

    def columns(self):
        return [
            "id",
            "summary",
            "type",
            "bugbug_type",
            "confidence",
            "confidences",
            "autofixed",
        ]

    def sort_columns(self):
        def _sort_columns(p):
            if (
                p[2] == "defect"
            ):  # defect -> non-defect is what we plan to autofix, so we show it first in the email.
                prio = 0
            elif (
                p[3] == "defect"
            ):  # non-defect -> defect has more priority than the rest, as 'enhancement' and 'task' can be often confused.
                prio = 1
            else:
                prio = 2

            # Then, we sort by confidence and ID.
            # p[0] is the id and is a string
            return (prio, -p[4], -int(p[0]))

        return _sort_columns

    def handle_bug(self, bug, data):
        # Summary and id are injected by BzCleaner.bughandler
        data[str(bug["id"])] = {"type": bug["type"]}
        return data

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        reporter_skiplist = self.get_config("reporter_skiplist", default=[])
        reporter_skiplist = ",".join(reporter_skiplist)

        return {
            "include_fields": ["id", "type"],
            # Ignore closed bugs.
            "bug_status": "__open__",
            # Check only recently opened bugs.
            "f1": "creation_ts",
            "o1": "greaterthan",
            "v1": start_date,
            "f2": "reporter",
            "o2": "nowords",
            "v2": reporter_skiplist,
            "f3": "bug_type",
            "o3": "everchanged",
            "n3": "1",
        }

    def get_bugs(self, date="today", bug_ids=[]):
        # Retrieve the bugs with the fields defined in get_bz_params
        raw_bugs = super().get_bugs(date=date, bug_ids=bug_ids, chunk_size=7000)

        if len(raw_bugs) == 0:
            return {}

        # Extract the bug ids
        bug_ids = list(raw_bugs.keys())

        # Classify those bugs
        bugs = get_bug_ids_classification("defectenhancementtask", bug_ids)

        results = {}

        for bug_id in sorted(bugs.keys()):
            bug_data = bugs[bug_id]

            if not bug_data.get("available", True):
                # The bug was not available, it was either removed or is a
                # security bug
                continue

            if not {"prob", "index", "class", "extra_data"}.issubset(bug_data.keys()):
                raise Exception(f"Invalid bug response {bug_id}: {bug_data!r}")

            bug = raw_bugs[bug_id]
            prob = bug_data["prob"]
            index = bug_data["index"]
            suggestion = bug_data["class"]
            labels_map = bug_data["extra_data"]["labels_map"]

            assert suggestion in {
                "defect",
                "enhancement",
                "task",
            }, f"Suggestion {suggestion} is invalid"

            if bug["type"] == suggestion:
                continue

            defect_prob = prob[labels_map["defect"]]
            enhancement_prob = prob[labels_map["enhancement"]]
            task_prob = prob[labels_map["task"]]

            results[bug_id] = {
                "id": bug_id,
                "summary": bug["summary"],
                "type": bug["type"],
                "bugbug_type": suggestion,
                "confidence": nice_round(prob[index]),
                "confidences": f"defect {nice_round(defect_prob)}, enhancement {nice_round(enhancement_prob)}, task {nice_round(task_prob)}",
                "autofixed": False,
            }

            # Only autofix results for which we are sure enough.
            # And only autofix defect -> task/enhancement for now, unless we're 100% sure.
            """if prob[index] == 1.0 or (
                bug["type"] == "defect"
                and (enhancement_prob + task_prob)
                >= self.get_config("confidence_threshold")
            ):"""
            if prob[index] == 1.0:
                results[bug_id]["autofixed"] = True
                self.autofix_type[bug["id"]] = suggestion

        return results

    def get_autofix_change(self):
        cc = self.get_config("cc")
        return {
            bug_id: {
                "type": suggestion,
                "cc": {"add": cc},
                "comment": {
                    "body": f"The [Bugbug](https://github.com/mozilla/bugbug/) bot thinks this bug is a [{suggestion}](https://firefox-source-docs.mozilla.org/bug-mgmt/guides/bug-types.html), but please change it back in case of error."
                },
            }
            for bug_id, suggestion in self.autofix_type.items()
        }


if __name__ == "__main__":
    DefectEnhancementTask().run()
