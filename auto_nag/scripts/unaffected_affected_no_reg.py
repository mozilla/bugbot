# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.bugzilla.utils import getVersions


class UnaffAffNoReg(BzCleaner):
    def __init__(self):
        super(UnaffAffNoReg, self).__init__()

    def description(self):
        return 'Bug not affecting the release but affecting beta or nightly without the regression keyword'

    def name(self):
        return 'unaffected_affected_no_reg'

    def template(self):
        return 'unaffected-affected-no-reg.html'

    def subject(self):
        return self.description()

    def ignore_date(self):
        return True

    def ignore_bug_summary(self):
        return False

    def get_bz_params(self, date):
        word_blacklist = self.get_config('word_blacklist', default=[])
        word_blacklist = '.*(' + '|'.join(word_blacklist) + ').*'
        release_version, beta_version, central_version, _ = getVersions()
        value = ','.join(['fixed', 'verified'])
        params = {
            'keywords': ['regression', 'feature'],
            'keywords_type': 'nowords',
            'short_desc_type': 'notregexp',
            'short_desc': word_blacklist,
            # not affecting release
            'f1': 'cf_status_firefox' + release_version,
            'o1': 'anyexact',
            'v1': 'unaffected',
            'f2': 'OP',
            'j2': 'OR',
            # affected in beta
            'f3': 'cf_status_firefox' + beta_version,
            'o3': 'anyexact',
            'v3': value,
            # affected in nightly
            'f4': 'cf_status_firefox' + central_version,
            'o4': 'anyexact',
            'v4': value,
            'f5': 'CP',
        }

        return params


if __name__ == '__main__':
    UnaffAffNoReg().run()
