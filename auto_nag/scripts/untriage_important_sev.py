# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class UntriagedWithImportantSev(BzCleaner):
    def __init__(self):
        super(UntriagedWithImportantSev, self).__init__()

    def description(self):
        return 'Get bugs in untriaged with an important severity'

    def name(self):
        return 'untriage_important_sev'

    def template(self):
        return 'untriage_important_sev.html'

    def subject(self):
        return self.description()

    def ignore_bug_summary(self):
        return False

    def get_bz_params(self, date):
        return {
            'resolution': ['---'],
            'bug_severity': ['blocker', 'critical', 'major'],
            'component': 'Untriaged',
        }


if __name__ == '__main__':
    UntriagedWithImportantSev().run()
