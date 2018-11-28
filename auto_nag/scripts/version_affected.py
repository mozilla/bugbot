# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bugzilla.utils import getVersions
from auto_nag.bzcleaner import BzCleaner


class VersionAffected(BzCleaner):
    def __init__(self):
        super(VersionAffected, self).__init__()
        _, self.beta_version, _ = getVersions()

    def description(self):
        return 'Bug with version set but not status_firefox'

    def name(self):
        return 'version_affected'

    def template(self):
        return 'version_affected.html'

    def subject(self):
        return self.description()

    def get_bz_params(self, date):
        params = {
            'resolution': ['---', 'FIXED'],
            'short_desc': '.*Risk Assessment.*',
            'short_desc_type': 'notregexp',
            'f1': 'cf_status_firefox' + self.beta_version,
            'o1': 'isempty',
            'version': self.beta_version + ' Branch',
        }

        return params


#    def get_autofix_change(self):
#        return {
#            'cf_status_firefox' + self.beta_version: 'affected'
#        }


if __name__ == '__main__':
    VersionAffected().run()
