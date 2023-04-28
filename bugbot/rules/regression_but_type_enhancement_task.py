# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner

TARGET_KEYWORDS = ["regression", "crash", "assertion"]


class RegressionButEnhancementTask(BzCleaner):
    def description(self):
        return (
            'Enhancement or task with the "regression", "crash" or "assertion" keyword'
        )

    def get_bz_params(self, date):
        days_lookup = self.get_config("days_lookup")
        params = {
            "include_fields": ["keywords"],
            "resolution": ["---", "FIXED"],
            "keywords": TARGET_KEYWORDS,
            "keywords_type": "anywords",
            "bug_type": ["task", "enhancement"],
            "f1": "days_elapsed",
            "o1": "lessthan",
            "v1": days_lookup,
        }
        return params

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        keywords = [
            f"`{keyword}`" for keyword in bug["keywords"] if keyword in TARGET_KEYWORDS
        ]

        self.autofix_changes[bugid] = {
            "type": "defect",
            "comment": {
                "body": (
                    f"This bug has the {utils.plural('keyword', keywords)} "
                    f"{utils.english_list(keywords)}, so its type should be defect."
                )
            },
        }

        return bug


if __name__ == "__main__":
    RegressionButEnhancementTask().run()
