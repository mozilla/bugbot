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
        return 'P3, P4 or P5 bugs without activity for {} months'.format(self.nmonths)

    def get_extra_for_template(self):
        return {'nmonths': self.nmonths}

    def ignore_meta(self):
        return True

    def has_product_component(self):
        return True

    def columns(self):
        return ['component', 'id', 'summary']

    def handle_bug(self, bug, data):
        # check if the product::component is in the list
        if not utils.check_pc(self.components, bug):
            return None
        return bug

    def get_bz_params(self, date):
        date = lmdutils.get_date_ymd(date)
        start_date = date - relativedelta(months=self.nmonths)
        days = (date - start_date).days
        self.components = utils.get_config('workflow', 'components')
        params = {
            'component': utils.get_components(self.components),
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
