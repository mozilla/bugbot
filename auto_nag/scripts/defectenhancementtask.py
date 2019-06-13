# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbug.models.defect_enhancement_task import DefectEnhancementTaskModel

from auto_nag.bugbug_utils import BugbugScript
from auto_nag.utils import nice_round


class DefectEnhancementTask(BugbugScript):
    def __init__(self):
        self.model_class = DefectEnhancementTaskModel
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
            return (prio, -p[4], -p[0])

        return _sort_columns

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        reporter_skiplist = self.get_config("reporter_skiplist", default=[])
        reporter_skiplist = ",".join(reporter_skiplist)

        return {
            # Ignore closed bugs.
            "bug_status": "__open__",
            # Check only recently opened bugs.
            "f1": "creation_ts",
            "o1": "greaterthan",
            "v1": start_date,
            "f2": "reporter",
            "o2": "nowords",
            "v2": reporter_skiplist,
        }

    # Remove bugs for which the type was already changed.
    def remove_using_history(self, bugs):
        def should_remove(bug):
            for h in bug["history"]:
                for change in h["changes"]:
                    if change["field_name"] == "type":
                        return True

            return False

        return [bug for bug in bugs if not should_remove(bug)]

    def get_bugs(self, date="today", bug_ids=[]):
        # Retrieve bugs to analyze.
        bugs = super().get_bugs_from_backend(
            "defectenhancementtask", date=date, bug_ids=bug_ids
        )
        if len(bugs) == 0:
            return {}

        # Apply inverse transformation to get the type name from the encoded labels.
        # TODO: Find a clean way to not need this
        labels = self.model.clf._le.inverse_transform([0, 1, 2])
        labels_map = {label: index for label, index in zip(labels, [0, 1, 2])}

        results = {}

        for bug_id in sorted(bugs.keys()):
            bug_data = bugs[bug_id]
            bug = bug_data["bug"]
            prob = bug_data["prob"]
            index = bug_data["index"]
            suggestion = bug_data["suggestion"]

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

            results[bug["id"]] = {
                "id": bug["id"],
                "summary": self.get_summary(bug),
                "type": bug["type"],
                "bugbug_type": suggestion,
                "confidence": nice_round(prob[index]),
                "confidences": f"defect {nice_round(defect_prob)}, enhancement {nice_round(enhancement_prob)}, task {nice_round(task_prob)}",
                "autofixed": False,
            }

            # Only autofix results for which we are sure enough.
            # And only autofix defect -> task/enhancement for now, unless we're 100% sure.
            if prob[index] == 1.0 or (
                bug["type"] == "defect"
                and (enhancement_prob + task_prob)
                >= self.get_config("confidence_threshold")
            ):
                results[bug["id"]]["autofixed"] = True
                self.autofix_type[bug["id"]] = suggestion

        return results

    def get_autofix_change(self):
        cc = self.get_config("cc")
        return {
            bug_id: {
                "type": suggestion,
                "cc": {"add": cc},
                "comment": {
                    "body": f"[Bugbug](https://github.com/mozilla/bugbug/) thinks this bug is a [{suggestion}](https://mozilla.github.io/bug-handling/bug-types), but please change it back in case of error."
                },
            }
            for bug_id, suggestion in self.autofix_type.items()
        }


if __name__ == "__main__":
    DefectEnhancementTask().run()
