# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.bugzilla.utils import getVersions
from auto_nag import utils


class MismatchPrioTrackESR(BzCleaner):
    def __init__(self):
        super(MismatchPrioTrackESR, self).__init__()

    def description(self):
        return 'Bug tracked for esr with a bad priority (P3, P4 or P5)'

    def name(self):
        return 'mismatch-priority-tracking'

    def template(self):
        return 'mismatch-priority-tracking.html'

    def subject(self):
        return self.description()

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        _, _, _, esr_version = getVersions()
        value = ','.join(['---', 'affected'])
        params = {
            'resolution': [
                '---',
                'FIXED',
                'INVALID',
                'WONTFIX',
                'DUPLICATE',
                'WORKSFORME',
                'INCOMPLETE',
                'SUPPORT',
                'EXPIRED',
                'MOVED',
            ],
            'priority': ['P3', 'P4', 'P5'],
            'f1': utils.get_flag(esr_version, 'tracking', 'esr'),
            'o1': 'anyexact',
            'v1': ','.join(['+', 'blocking']),
            'f2': utils.get_flag(esr_version, 'status', 'esr'),
            'o2': 'anyexact',
            'v2': value,
        }
        return params

    def get_autofix_change(self):
        return {
            'comment': {
                'body': 'Changing the priority to p1 as the bug is tracked by a release manager for the current esr.\nSee https://github.com/mozilla/bug-handling/blob/master/policy/triage-bugzilla.md#how-do-you-triage for more information'
            },
            'priority': 'p1',
        }


if __name__ == '__main__':
    MismatchPrioTrackESR().run()
