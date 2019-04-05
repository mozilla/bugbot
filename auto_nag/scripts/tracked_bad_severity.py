# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class TrackedBadSeverity(BzCleaner):
    def __init__(self):
        super(TrackedBadSeverity, self).__init__()
        self.versions = utils.get_checked_versions()

    def description(self):
        return 'Bug tracked in a release but with a small severity'

    def ignore_date(self):
        return True

    def has_enough_data(self):
        return bool(self.versions)

    def get_bz_params(self, date):
        # TODO add support for ESR here?
        value = ','.join(['affected', 'fixed'])
        params = {
            'bug_severity': ['normal', 'minor', 'trivial', 'enhancement'],
            'f1': 'OP',
            'j1': 'OR',
            'f2': 'OP',
            'f3': utils.get_flag(self.versions['release'], 'tracking', 'release'),
            'o3': 'equals',
            'v3': 'blocking',
            'f4': utils.get_flag(self.versions['release'], 'status', 'release'),
            'o4': 'anyexact',
            'v4': value,
            'f5': 'CP',
            'f6': 'OP',
            'f7': utils.get_flag(self.versions['beta'], 'tracking', 'beta'),
            'o7': 'equals',
            'v7': 'blocking',
            'f8': utils.get_flag(self.versions['beta'], 'status', 'beta'),
            'o8': 'anyexact',
            'v8': value,
            'f9': 'CP',
            'f10': 'OP',
            'f11': utils.get_flag(self.versions['central'], 'tracking', 'central'),
            'o11': 'equals',
            'v11': 'blocking',
            'f12': utils.get_flag(self.versions['central'], 'status', 'central'),
            'o12': 'anyexact',
            'v12': value,
            'f13': 'CP',
            'f14': 'CP',
        }

        return params

    def get_autofix_change(self):
        return {'severity': 'major'}


if __name__ == '__main__':
    TrackedBadSeverity().run()
