# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class TaskEnhancementRegression(BzCleaner):
    def __init__(self):
        super(TaskEnhancementRegression, self).__init__()
        self.threshold = self.get_config("threshold")
        self.ndays = self.get_config("days_lookup")
        self.regressors = {}

    def description(self):
        return (
            f"Task or enhancement which caused more than {self.threshold} regressions"
        )

    def get_extra_for_template(self):
        return {"threshold": self.threshold}

    def has_product_component(self):
        return True

    def columns(self):
        return ["id", "summary", "product", "component"]

    def handle_bug(self, bug, data):
        if len(bug["regressions"]) < self.threshold:
            return None

        return bug

    def get_bz_params(self, date):
        fields = ["regressions"]
        params = {
            "include_fields": fields,
            "f1": "bug_type",
            "o1": "anywords",
            "v1": "task,enhancement",
            "f2": "regresses",
            "o2": "isnotempty",
            "f3": "creation_ts",
            "o3": "greaterthaneq",
            "v3": "-{self.ndays}d",
        }

        return params


if __name__ == "__main__":
    TaskEnhancementRegression().run()
