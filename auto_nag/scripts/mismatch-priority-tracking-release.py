# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.bugzilla.utils import getVersions


class MismatchPrioTrackRelease(BzCleaner):
    def __init__(self):
        super(MismatchPrioTrackRelease, self).__init__()

    def description(self):
        return 'Bug tracked for release with a bad priority (P3, P4 or P5)'

    def name(self):
        return 'mismatch-priority-tracking'

    def template(self):
        return 'mismatch-priority-tracking.html'

    def subject(self):
        return self.description()

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        release_version, _, _, _ = getVersions()
        value = ','.join(['', 'affected'])
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
            'f1': 'OP',
            'f2': 'cf_tracking_firefox' + release_version,
            'o2': 'anyexact',
            'v2': ','.join(['+', 'blocking']),
            'f3': 'cf_status_firefox' + release_version,
            'o3': 'anyexact',
            'v3': value,
            'o4': 'anyexact',
            'f5': 'CP',
            'o6': 'notsubstring',
        }
        return params

    def get_autofix_change(self):
        return {
            'comment': {
                'body': 'Changing the priority to p1 as the bug is tracked by a release manager for the current beta.\nSee https://github.com/mozilla/bug-handling/blob/master/policy/triage-bugzilla.md#how-do-you-triage for more information'
            },
            'priority': 'p1',
        }



if __name__ == '__main__':
    MismatchPrioTrackRelease().run()
