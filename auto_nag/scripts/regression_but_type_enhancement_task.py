# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class RegressionButEnhancementTask(BzCleaner):
    def description(self):
        return (
            'Enhancement or task with the "regression", "crash" or "assertion" keyword'
        )

    def get_bz_params(self, date):
        days_lookup = self.get_config("days_lookup")
        params = {
            "resolution": ["---", "FIXED"],
            "keywords": ["regression", "crash", "assertion"],
            "keywords_type": "anywords",
            "bug_type": ["task", "enhancement"],
            "f1": "days_elapsed",
            "o1": "lessthan",
            "v1": days_lookup,
        }
        return params

    def get_autofix_change(self):
        return {"type": "defect"}


if __name__ == "__main__":
    RegressionButEnhancementTask().run()
