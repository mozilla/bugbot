# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.people import People


class HasSTRNoRange(BzCleaner):
    def __init__(self):
        super(HasSTRNoRange, self).__init__()
        self.people = People()
        self.autofix_reporters = {}

    def description(self):
        return 'Get the bugs with a STR and no regression range'

    def name(self):
        return 'has_str_no_range'

    def template(self):
        return 'has_str_no_range.html'

    def subject(self):
        return 'Bugs with STR and no regression range'

    def ignore_bug_summary(self):
        return False

    def has_individual_autofix(self):
        return True

    def get_autofix_change(self):
        return self.autofix_reporters

    def handle_bug(self, bug, data):
        creator = bug['creator']
        if self.people.is_mozilla(creator):
            return bug

        bugid = str(bug['id'])
        nick = bug['creator_detail']['nick']
        self.autofix_reporters[bugid] = {
            'keywords': {'add': ['regressionwindow-wanted']},
            'comment': {
                'body': ':{}, could try to find a regression range in using for example [mozregression](https://wiki.mozilla.org/Auto-tools/Projects/Mozregression)?'.format(
                    nick
                )
            },
        }

        return bug

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        fields = ['creator']
        params = {
            'include_fields': fields,
            'resolution': '---',
            'f1': 'creation_ts',
            'o1': 'greaterthan',
            'v1': start_date,
            'f2': 'cf_has_regression_range',
            'o2': 'equals',
            'v2': '---',
            'n3': 1,
            'f3': 'cf_has_regression_range',
            'o3': 'changedafter',
            'v3': start_date,
            'f4': 'cf_has_str',
            'o4': 'equals',
            'v4': 'yes',
        }

        return params


if __name__ == '__main__':
    HasSTRNoRange().run()
