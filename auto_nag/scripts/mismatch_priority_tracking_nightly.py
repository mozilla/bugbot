# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class MismatchPrioTrackNightly(BzCleaner):
    def __init__(self):
        super(MismatchPrioTrackNightly, self).__init__()

    def description(self):
        return 'Bug tracked for nightly with a bad priority (P3, P4 or P5)'

    def template(self):
        return 'mismatch_priority_tracking.html'

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        central_version = utils.get_versions(channel='central')
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
            'f1': 'cf_tracking_firefox' + central_version,
            'o1': 'anyexact',
            'v1': ','.join(['+', 'blocking']),
            'f2': 'cf_status_firefox' + central_version,
            'o2': 'anyexact',
            'v2': value,
        }
        return params

    def get_autofix_change(self):
        return {
            'comment': {
                'body': 'Changing the priority to p2 as the bug is tracked by a release manager for the current nightly.\nSee [What Do You Triage](https://mozilla.github.io/bug-handling/triage-bugzilla#what-do-you-triage) for more information'
            },
            'priority': 'p2',
        }


if __name__ == '__main__':
    MismatchPrioTrackNightly().run()
