# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.bugzilla.utils import getVersions


class TrackedBadSeverity(BzCleaner):
    def __init__(self):
        super(TrackedBadSeverity, self).__init__()

    def description(self):
        return 'Bug tracked in a release but with a small severity'

    def name(self):
        return 'tracked_bad_severity'

    def template(self):
        return 'tracked-bad-severity.html'

    def subject(self):
        return self.description()

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        release_version, beta_version, central_version = getVersions()
        value = ','.join(['affected', 'fixed'])
        params = {
            'bug_severity': ['normal', 'minor', 'trivial', 'enhancement'],
            'f1': 'OP',
            'j1': 'OR',
            'f2': 'OP',
            'f3': 'cf_tracking_firefox' + release_version,
            'o3': 'equals',
            'v3': 'blocking',
            'f4': 'cf_status_firefox' + release_version,
            'o4': 'anyexact',
            'v4': value,
            'f5': 'CP',
            'f6': 'OP',
            'f7': 'cf_tracking_firefox' + beta_version,
            'o7': 'equals',
            'v7': 'blocking',
            'f8': 'cf_status_firefox' + beta_version,
            'o8': 'anyexact',
            'v8': value,
            'f9': 'CP',
            'f10': 'OP',
            'f11': 'cf_tracking_firefox' + central_version,
            'o11': 'equals',
            'v11': 'blocking',
            'f12': 'cf_status_firefox' + central_version,
            'o12': 'anyexact',
            'v12': value,
            'f13': 'CP',
            'f14': 'CP',
        }

        return params


if __name__ == '__main__':
    TrackedBadSeverity().run()
