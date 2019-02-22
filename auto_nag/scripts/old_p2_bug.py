# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class oldP2Bug(BzCleaner):
    def __init__(self):
        super(oldP2Bug, self).__init__()
        self.nyears = utils.get_config(self.name(), 'number_of_years', 1)

    def description(self):
        return 'Get old P2 bugs without activity for the last {} year'.format(
            self.nyears, utils.plural('year', self.nyears)
        )

    def name(self):
        return 'old-p2-bug'

    def template(self):
        return 'old_p2_bug.html'

    def subject(self):
        return self.description()

    def get_extra_for_template(self):
        return {'nyears': self.nyears}

    def ignore_bug_summary(self):
        return False

    def get_bz_params(self, date):
        params = {
            'resolution': '---',
            'priority': 'p2',
            'f1': 'days_elapsed',
            'o1': 'greaterthan',
            'v1': self.nyears * 365,
        }

        return params

    def get_autofix_change(self):
        return {
            'comment': {
                'body': 'Moving to p3 because no activity for at least {} {}.\nSee [How Do You Triage](https://mozilla.github.io/bug-handling/triage-bugzilla#how-do-you-triage) for more information'.format(
                    self.nyears, utils.plural('year', self.nyears)
                )
            },
            'priority': 'p3',
        }


if __name__ == '__main__':
    oldP2Bug().run()
