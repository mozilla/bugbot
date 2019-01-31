# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class P3P4P5(BzCleaner):
    def __init__(self):
        super(P3P4P5, self).__init__()
        self.nmonths = utils.get_config(self.name(), 'months_lookup', 6)

    def description(self):
        return 'Get P3, P4 and P5 bugs and no activity for {} months'.format(
            self.nmonths
        )

    def name(self):
        return 'workflow-p3-p4-p5'

    def template(self):
        return 'workflow_p3_p4_p5.html'

    def subject(self):
        return 'P3, P4 or P5 bugs without activity for {} months'.format(self.nmonths)

    def get_extra_for_template(self):
        return {'nmonths': self.nmonths}

    def ignore_bug_summary(self):
        return False

    def has_product_component(self):
        return True

    def get_bz_params(self, date):
        date = lmdutils.get_date_ymd(date)
        start_date = date - relativedelta(months=self.nmonths)
        days = (date - start_date).days
        comps = utils.get_config('workflow', 'components')
        params = {
            'component': comps,
            'resolution': '---',
            'f1': 'priority',
            'o1': 'anywordssubstr',
            'v1': ','.join(['P3', 'P4', 'P5']),
            'f2': 'days_elapsed',
            'o2': 'greaterthaneq',
            'v2': days,
        }
        return params

    def get_autofix_change(self):
        return {
            'comment': {
                'body': 'Resolve the bug as INACTIVE since there is no activity for {} months.\nSee [How Do You Triage](https://mozilla.github.io/bug-handling/triage-bugzilla#how-do-you-triage) for more information.'.format(
                    self.nmonths
                )
            },
            'status': 'RESOLVED',
            'resolution': 'INACTIVE',
        }


if __name__ == '__main__':
    P3P4P5().run()
