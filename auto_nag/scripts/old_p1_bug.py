# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class oldP1Bug(BzCleaner):
    def __init__(self):
        super(oldP1Bug, self).__init__()
        self.nweeks = utils.get_config(self.name(), 'number_of_weeks', 24)

    def description(self):
        return 'Get old P1 bugs with no activity for the last {} weeks'.format(
            self.nweeks
        )

    def name(self):
        return 'old-p1-bug'

    def template(self):
        return 'old_p1_bug.html'

    def subject(self):
        return self.description()

    def get_extra_for_template(self):
        return {'nweeks': self.nweeks}

    def ignore_bug_summary(self):
        return False

    def get_bz_params(self, date):
        params = {
            'resolution': '---',
            'priority': 'p1',
            'f1': 'days_elapsed',
            'o1': 'greaterthan',
            'v1': self.nweeks * 7,
        }

        return params

    def get_autofix_change(self):
        return {
            'comment': {
                'body': 'Moving to p3 because no activity for at least {} weeks.\nSee https://github.com/mozilla/bug-handling/blob/master/policy/triage-bugzilla.md#how-do-you-triage for more information'.format(
                    self.nweeks
                )
            },
            'priority': 'p3',
        }


if __name__ == '__main__':
    oldP1Bug().run()
