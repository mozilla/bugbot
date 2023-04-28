# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.bzcleaner import BzCleaner


class FeatureRegression(BzCleaner):
    def description(self):
        return "Bugs with feature and regression keywords"

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        return {
            "resolution": ["---", "FIXED"],
            "keywords": ["feature", "regression"],
            "keywords_type": "allwords",
        }


if __name__ == "__main__":
    FeatureRegression().run()
