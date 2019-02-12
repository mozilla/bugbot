# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.escalation import Escalation
from auto_nag.nag_me import Nag
from auto_nag import utils


class P2NoActivity(BzCleaner, Nag):
    def __init__(self):
        super(P2NoActivity, self).__init__()
        self.nmonths = utils.get_config(self.name(), 'months_lookup', 3)
        self.escalation = Escalation(
            self.people,
            data=utils.get_config(self.name(), 'escalation'),
            blacklist=utils.get_config('workflow', 'supervisor_blacklist', []),
        )

    def description(self):
        return 'Get P2 bugs and no activity for {} months'.format(self.nmonths)

    def name(self):
        return 'workflow-p2-no-activity'

    def template(self):
        return 'workflow_p2_no_activity.html'

    def nag_template(self):
        return self.template()

    def subject(self):
        return 'P2 bugs without activity for {} months'.format(self.nmonths)

    def get_extra_for_template(self):
        return {'nmonths': self.nmonths}

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def ignore_bug_summary(self):
        return False

    def ignore_meta(self):
        return True

    def has_last_comment_time(self):
        return True

    def has_product_component(self):
        return True

    def columns(self):
        return ['component', 'id', 'summary', 'last_comment']

    def set_people_to_nag(self, bug, buginfo):
        priority = 'default'
        if not self.filter_bug(priority):
            return None

        owner = bug['triage_owner']
        self.add_triage_owner(owner, utils.get_config('workflow', 'components'))
        if not self.add(owner, buginfo, priority=priority):
            self.add_no_manager(buginfo['id'])
        return bug

    def get_bz_params(self, date):
        date = lmdutils.get_date_ymd(date)
        start_date = date - relativedelta(months=self.nmonths)
        days = (date - start_date).days
        fields = ['triage_owner']
        comps = utils.get_config('workflow', 'components')
        params = {
            'include_fields': fields,
            'component': comps,
            'resolution': '---',
            'f1': 'priority',
            'o1': 'equals',
            'v1': 'P2',
            'f2': 'days_elapsed',
            'o2': 'greaterthaneq',
            'v2': days,
        }
        return params


if __name__ == '__main__':
    P2NoActivity().run()
