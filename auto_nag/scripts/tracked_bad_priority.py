# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.bugzilla.utils import getVersions


class TrackedBadPriority(BzCleaner):
    def __init__(self):
        super(TrackedBadPriority, self).__init__()

    def description(self):
        return 'Bug tracked in nightly, beta and release but with a weak priority'

    def name(self):
        return 'tracked_bad_priority'

    def template(self):
        return 'tracked-bad-priority.html'

    def subject(self):
        return self.description()

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        release_version, beta_version, central_version = getVersions()
        params = {
            'priority': ['P3', 'P4', 'P5'],
            'resolution': '---',
            'f1': 'cf_tracking_firefox' + release_version,
            'o1': 'anyexact',
            'v1': '+,blocking',
            'f2': 'cf_tracking_firefox' + beta_version,
            'o2': 'anyexact',
            'v2': '+,blocking',
            'f3': 'cf_tracking_firefox' + central_version,
            'o3': 'anyexact',
            'v3': '+,blocking',
        }

        return params


if __name__ == '__main__':
    TrackedBadPriority().run()
