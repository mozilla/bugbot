# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbug.models.regression import RegressionModel

from auto_nag.bugbug_utils import BugbugScript
from auto_nag.utils import nice_round


class Regression(BugbugScript):
    def __init__(self):
        self.model_class = RegressionModel
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

    # Remove bugs for which the regression keyword was set and removed in the past.
    def remove_using_history(self, bugs):
        def should_remove(bug):
            for h in bug["history"]:
                for change in h["changes"]:
                    # N.B.: The removed field can be a comma-separated list.
                    if change["field_name"] == "keywords" and "regression" in [
                        key.strip() for key in change["removed"].split(",")
                    ]:
                        return True

            return False

        return [bug for bug in bugs if not should_remove(bug)]

    def get_bugs(self, date="today", bug_ids=[]):
        # Retrieve bugs to analyze.
        bugs, probs = super().get_bugs(date=date, bug_ids=bug_ids)
        if len(bugs) == 0:
            return {}

        result = {}
        for bug, prob in zip(bugs, probs):
            if prob[1] < 0.5:
                continue

            bug_id = str(bug["id"])
            result[bug_id] = {
                "id": bug_id,
                "summary": self.get_summary(bug),
                "confidence": nice_round(prob[1]),
                "autofixed": False,
            }

            # Only autofix results for which we are sure enough.
            if prob[1] >= self.get_config("confidence_threshold"):
                result[bug_id]["autofixed"] = True
                self.autofix_regression.append((bug_id, prob[1]))

        return result

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
                    "body": "[Bugbug](https://github.com/mozilla/bugbug/) thinks this bug is a regression, but please revert this change in case of error."
                }

        return autofix_change


if __name__ == "__main__":
    Regression().run()
