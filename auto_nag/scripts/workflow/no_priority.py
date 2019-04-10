# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils
from auto_nag.escalation import Escalation
from auto_nag.nag_me import Nag
from auto_nag.round_robin import RoundRobin


class NoPriority(BzCleaner, Nag):
    def __init__(self, typ):
        super(NoPriority, self).__init__()
        assert typ in {'first', 'second'}
        self.typ = typ
        self.lookup_first = utils.get_config(self.name(), 'first-step', 2)
        self.lookup_second = utils.get_config(self.name(), 'second-step', 4)
        self.escalation = Escalation(
            self.people,
            data=utils.get_config(self.name(), 'escalation-{}'.format(typ)),
            blacklist=utils.get_config('workflow', 'supervisor_blacklist', []),
        )
        self.round_robin = RoundRobin(people=self.people)

    def description(self):
        return 'Bugs without a priority set'

    def nag_template(self):
        return self.template()

    def get_extra_for_template(self):
        return {
            'nweeks': self.lookup_first if self.typ == 'first' else self.lookup_second
        }

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def has_product_component(self):
        return True

    def ignore_meta(self):
        return True

    def columns(self):
        return ['component', 'id', 'summary']

    def get_mail_to_auto_ni(self, bug):
        if self.typ == 'second':
            return None

        mail, nick = self.round_robin.get(bug, self.date)
        return {'mail': mail, 'nickname': nick}

    def set_people_to_nag(self, bug, buginfo):
        priority = 'default'
        if not self.filter_bug(priority):
            return None

        # check if the product::component is in the list
        if not utils.check_pc(self.components, bug):
            return None

        owner, _ = self.round_robin.get(bug, self.date)
        real_owner = bug['triage_owner']
        self.add_triage_owner(
            owner, utils.get_config('workflow', 'components'), real_owner=real_owner
        )
        if not self.add(owner, buginfo, priority=priority):
            self.add_no_manager(buginfo['id'])
        return bug

    def get_bz_params(self, date):
        fields = ['triage_owner', 'flags']
        self.components = utils.get_config('workflow', 'components')
        params = {
            'component': utils.get_components(self.components),
            'include_fields': fields,
            'resolution': '---',
            'f1': 'priority',
            'o1': 'equals',
            'v1': '--',
        }
        self.date = lmdutils.get_date_ymd(date)
        if self.typ == 'first':
            params.update(
                {
                    'f2': 'flagtypes.name',
                    'o2': 'notequals',
                    'v2': 'needinfo?',
                    'f3': 'creation_ts',
                    'o3': 'lessthaneq',
                    'v3': self.date - relativedelta(days=self.lookup_first * 7),
                    'f4': 'creation_ts',
                    'o4': 'greaterthan',
                    'v4': self.date - relativedelta(days=self.lookup_second * 7),
                }
            )
        else:
            params.update(
                {
                    'f2': 'creation_ts',
                    'o2': 'lessthaneq',
                    'v2': self.date - relativedelta(days=self.lookup_second * 7),
                }
            )

        return params


if __name__ == '__main__':
    NoPriority('first').run()
    NoPriority('second').run()
