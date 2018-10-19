# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.bugzilla.utils import getVersions


class MismatchPrioTrack(BzCleaner):

    def __init__(self):
        super(MismatchPrioTrack, self).__init__()

    def description(self):
        return 'Bug tracked with a bad priority'

    def name(self):
        return 'mismatch-priority-tracking'

    def template(self):
        return 'mismatch-priority-tracking.html'

    def subject(self):
        return self.description()

    def ignore_date(self):
        return True

    def get_bz_params(self, date):

        release_version, beta_version, central_version = getVersions()
        params = {'resolution': ['---', 'FIXED',
                                 'INVALID', 'WONTFIX',
                                 'DUPLICATE', 'WORKSFORME',
                                 'INCOMPLETE', 'SUPPORT',
                                 'EXPIRED', 'MOVED'],
                  'j_top': 'OR',
                  'priority': ['p4', 'p5'],
                  'f1': 'cf_tracking_firefox' + release_version,
                  'o1': 'anyexact',
                  'v1': ['+', 'blocking'],
                  'f2': 'cf_tracking_firefox' + beta_version,
                  'o2': 'anyexact',
                  'v2': ['+', 'blocking'],
                  'f3': 'cf_tracking_firefox' + central_version,
                  'o3': 'anyexact',
                  'v3': ['+', 'blocking'],
                  }

        return params


if __name__ == '__main__':
    MismatchPrioTrack().run()
