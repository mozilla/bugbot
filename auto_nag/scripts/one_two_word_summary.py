# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class OneTwoWordSummary(BzCleaner):
    def __init__(self):
        super(OneTwoWordSummary, self).__init__()

    def description(self):
        return 'Get bugs with only one or two words in the summary'

    def name(self):
        return 'one_two_word_summary'

    def template(self):
        return 'one_two_word_summary.html'

    def subject(self):
        return self.description()

    def ignore_bug_summary(self):
        return False

    def get_bz_params(self, date):
        days_lookup = self.get_config('days_lookup', default=7)
        return {
            'resolution': ['---'],
            'short_desc': '^([a-zA-Z0-9_]+ [a-zA-Z0-9_]+|[a-zA-Z0-9_]+)$',
            'short_desc_type': 'regexp',
            'f1': 'days_elapsed',
            'o1': 'lessthan',
            'v1': days_lookup,
        }


if __name__ == '__main__':
    OneTwoWordSummary().run()
