# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils
from auto_nag.escalation import Escalation
from auto_nag.nag_me import Nag


class NoPriority(BzCleaner, Nag):
    def __init__(self, typ):
        super(NoPriority, self).__init__()
        assert typ in {'first', 'second'}
        self.typ = typ
        self.lookup_first = utils.get_config(self.name(), 'first-step', 2)
        self.lookup_second = utils.get_config(self.name(), 'second-step', 4)
        self.escalation = Escalation(
            self.people,
            data=utils.get_config(self.name(), 'escalation'),
            blacklist=utils.get_config('workflow', 'supervisor_blacklist', []),
        )

    def description(self):
        return 'Bugs without a priority set'

    def name(self):
        return 'workflow-no-priority'

    def template(self):
        return 'workflow_no_priority.html'

    def needinfo_template(self):
        return 'workflow_no_priority_comment.txt'

    def nag_template(self):
        return self.template()

    def subject(self):
        return 'Bugs without a priority set'

    def get_extra_for_template(self):
        return {
            'nweeks': self.lookup_first if self.typ == 'first' else self.lookup_second
        }

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def ignore_bug_summary(self):
        return False

    def has_product_component(self):
        return True

    def ignore_meta(self):
        return True

    def columns(self):
        return ['component', 'id', 'summary']

    def get_mail_to_auto_ni(self, bug):
        if self.typ == 'second':
            return None

        mail = bug['triage_owner']
        nick = bug['triage_owner_detail']['nick']
        return {'mail': mail, 'nickname': nick}

    def set_people_to_nag(self, bug, buginfo):
        if self.typ == 'first':
            return bug

        priority = 'default'
        if not self.filter_bug(priority):
            return None

        owner = bug['triage_owner']
        self.add_triage_owner(owner, utils.get_config('workflow', 'components'))
        if not self.add(owner, buginfo, priority=priority):
            self.add_no_manager(buginfo['id'])
        return bug

    def get_bz_params(self, date):
        fields = ['triage_owner', 'flags']
        comps = utils.get_config('workflow', 'components')
        params = {
            'component': comps,
            'bug_id': '1523291',
            'include_fields': fields,
            'resolution': '---',
            'f1': 'priority',
            'o1': 'equals',
            'v1': '--',
        }
        date = lmdutils.get_date_ymd(date)
        if self.typ == 'first':
            params.update(
                {
                    'f2': 'flagtypes.name',
                    'o2': 'notequals',
                    'v2': 'needinfo?',
                    'f3': 'creation_ts',
                    'o3': 'lessthaneq',
                    'v3': date - relativedelta(days=self.lookup_first * 7),
                    'f4': 'creation_ts',
                    'o4': 'greaterthan',
                    'v4': date - relativedelta(days=self.lookup_second * 7),
                }
            )
        else:
            params.update(
                {
                    'f2': 'creation_ts',
                    'o2': 'lessthaneq',
                    'v2': date - relativedelta(days=self.lookup_second * 7),
                }
            )

        return params


if __name__ == '__main__':
    NoPriority('first').run()
    NoPriority('second').run()

"""    
1) your first case (no priority + pending ni), we will ignore these pattern. If the bot notices this pattern and without any activity for X days,
we will need info the official triage owner to act on the bug (INCOMPLETE for example)
"""
