# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class MetaDefect(BzCleaner):
    def __init__(self):
        super(MetaDefect, self).__init__()
        self.nmonths = utils.get_config(self.name(), 'months_lookup')

    def description(self):
        return 'Task with the "meta" keyword with activity for the last {} months'.format(
            self.nmonths
        )

    def get_bz_params(self, date):
        params = {
            "resolution": "---",
            "keywords": "meta",
            "keywords_type": "allwords",
            "bug_type": ["defect"],
            'f1': 'days_elapsed',
            'o1': 'lessthan',
            'v1': self.nmonths * 30,
        }
        return params


if __name__ == "__main__":
    MetaDefect().run()
