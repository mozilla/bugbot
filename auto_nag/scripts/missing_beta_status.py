# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.common import get_current_versions
from auto_nag import utils


class MissingBetaStatus(BzCleaner):
    def __init__(self):
        super(MissingBetaStatus, self).__init__()
        self.autofix_status = {}

    def description(self):
        return 'Bug with a missing beta status flag'

    def name(self):
        return 'missing_beta_status'

    def template(self):
        return 'missing-beta-status.html'

    def subject(self):
        return self.description()

    def ignore_date(self):
        return True

    def has_individual_autofix(self):
        return True

    def get_autofix_change(self):
        return self.autofix_status

    def ignore_bug_summary(self):
        return False

    def handle_bug(self, bug):
        bugid = str(bug['id'])
        central = bug[self.status_central]
        release = bug[self.status_release]

        if central == release and release != "verified":
            self.autofix_status[bugid] = {self.status_beta: central}
        else:
            # if the two status are different, we don't know what to set
            # if this verified on nightly and release, we cannot say
            # per say if this is verified
            self.autofix_status[bugid] = {self.status_beta: '?'}

    def get_bz_params(self, date):
        versions = get_current_versions()
        self.status_central = utils.get_flag(versions['central'], 'status', 'central')
        self.status_release = utils.get_flag(versions['release'], 'status', 'release')
        self.status_beta = utils.get_flag(versions['beta'], 'status', 'beta')
        fields = [self.status_central, self.status_release]
        params = {
            'include_fields': fields,
            'f1': self.status_beta,
            'o1': 'equals',
            'v1': '---',
            'f2': self.status_release,
            'o2': 'notequals',
            'v2': '---',
            'f3': self.status_central,
            'o3': 'notequals',
            'v3': '---',
        }

        return params


if __name__ == '__main__':
    MissingBetaStatus().run()
