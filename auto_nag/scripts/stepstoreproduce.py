# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbug.models.stepstoreproduce import StepsToReproduceModel

from auto_nag.bugbug_utils import BugbugScript
from auto_nag.utils import nice_round


class StepsToReproduce(BugbugScript):
    def __init__(self):
        self.model_class = StepsToReproduceModel
        super().__init__()

    def description(self):
        return "[Using ML] Bugs with missing steps to reproduce"

    def columns(self):
        return ["id", "summary", "has_str", "confidence", "autofixed"]

    def sort_columns(self):
        return lambda p: (-p[3], -int(p[0]))

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)

        reporter_skiplist = self.get_config("reporter_skiplist", default=[])
        reporter_skiplist = ",".join(reporter_skiplist)

        params = {
            "bug_type": "defect",
            "f1": "longdesc",
            "o1": "changedafter",
            "v1": start_date,
            "f2": "longdesc",
            "o2": "changedbefore",
            "v2": end_date,
            "f3": "reporter",
            "o3": "nowords",
            "v3": reporter_skiplist,
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
        # Retrieve bugs to analyze.
        bugs, probs = super().get_bugs(date=date, bug_ids=bug_ids)
        if len(bugs) == 0:
            return {}

        indexes = probs.argmax(axis=-1)

        result = {}
        for bug, prob, index in zip(bugs, probs, indexes):
            bug_id = str(bug["id"])
            result[bug_id] = {
                "id": bug_id,
                "summary": self.get_summary(bug),
                "has_str": "yes" if prob[1] > 0.5 else "no",
                "confidence": nice_round(prob[index]),
                "autofixed": False,
            }

        return result

    def get_autofix_change(self):
        return {}


if __name__ == "__main__":
    StepsToReproduce().run()
