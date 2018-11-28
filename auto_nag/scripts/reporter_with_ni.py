# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class ReporterWithNI(BzCleaner):
    def __init__(self):
        super(ReporterWithNI, self).__init__()
        self.nweeks = utils.get_config(self.name(), 'number_of_weeks', 12)

    def description(self):
        return 'Get bugs where the reporter has a needinfo and no activity for the last {} weeks'.format(
            self.nweeks
        )

    def name(self):
        return 'reporter-with-ni'

    def template(self):
        return 'reporter_with_ni.html'

    def subject(self):
        return 'Bugs where the reporter has a needinfo and no activity for the last {} weeks'.format(
            self.nweeks
        )

    def get_extra_for_template(self):
        return {'nweeks': self.nweeks}

    def ignore_bug_summary(self):
        return False

    def get_bz_params(self, date):
        params = {
            'resolution': '---',
            'f1': 'flagtypes.name',
            'o1': 'substring',
            'v1': 'needinfo?',
            'f2': 'days_elapsed',
            'o2': 'greaterthan',
            'v2': self.nweeks * 7,
            'include_fields': ['creator', 'flags'],
        }

        return params

    def bughandler(self, bug, data):
        creator = bug['creator']
        for flag in bug['flags']:
            if flag.get('name', '') != 'needinfo':
                continue
            if 'requestee' not in flag:
                continue
            if flag['requestee'] == creator:
                super(ReporterWithNI, self).bughandler(bug, data)


if __name__ == '__main__':
    ReporterWithNI().run()
