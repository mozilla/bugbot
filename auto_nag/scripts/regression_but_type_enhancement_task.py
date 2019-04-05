# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class RegressionButEnhancementTask(BzCleaner):
    def __init__(self):
        super(RegressionButEnhancementTask, self).__init__()

    def description(self):
        return 'Enhancement or task with the "regression" keyword'

    def get_bz_params(self, date):
        params = {
            "resolution": "---",
            "keywords": "regression",
            "keywords_type": "allwords",
            "bug_type": ["task", "enhancement"],
        }
        return params


if __name__ == "__main__":
    RegressionButEnhancementTask().run()
