# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.common import get_current_versions
from auto_nag import utils


class NightlyReopened(BzCleaner):
    def __init__(self):
        super(NightlyReopened, self).__init__()
        versions = get_current_versions()
        self.nightly = utils.get_flag(versions['central'], 'status', 'nightly')
        self.beta = utils.get_flag(versions['beta'], 'status', 'beta')
        self.release = utils.get_flag(versions['release'], 'status', 'release')
        self.esr = utils.get_flag(versions['esr'], 'status', 'esr')

    def description(self):
        return 'Get the reopened bugs with status flag for nightly not up-to-date'

    def name(self):
        return 'nightly-reopened'

    def template(self):
        return 'nightly_reopened.html'

    def subject(self):
        return self.description()

    def ignore_bug_summary(self):
        return False

    def get_bz_params(self, date):
        unaffected = ','.join(['---', 'unaffected'])
        params = {
            'bug_status': 'REOPENED',
            'resolution': '---',
            'f1': self.nightly,
            'o1': 'anyexact',
            'v1': ','.join(['wontfix', 'fixed']),
            'f2': self.beta,
            'o2': 'anyexact',
            'v2': unaffected,
            'f3': self.release,
            'o3': 'anyexact',
            'v3': unaffected,
            'f4': self.esr,
            'o4': 'anyexact',
            'v4': unaffected,
        }

        return params

    def get_autofix_change(self):
        return {self.nightly: 'affected'}


if __name__ == '__main__':
    NightlyReopened().run()
