# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class OneWordSummary(BzCleaner):

    def __init__(self):
        super(OneWordSummary, self).__init__()

    def description(self):
        return 'Get bugs with only one word in the summary'

    def name(self):
        return 'one_word_summary'

    def template(self):
        return 'one_word_summary.html'

    def subject(self):
        return self.description()

    def ignore_date(self):
        return True

    def ignore_bug_summary(self):
        return False

    def get_bz_params(self, date):
        return {'resolution': ['---'],
                'bug_status': ['UNCONFIRMED', 'NEW', 'ASSIGNED', 'REOPENED'],
                'short_desc': '^[a-zA-Z0-9_]+$',
                'short_desc_type': 'regexp'}


if __name__ == '__main__':
    OneWordSummary().run()
