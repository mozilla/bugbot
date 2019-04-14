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
        if not utils.check_product_component(self.components, bug):
            return None

        # don't nag in the first step (just a ni is enough)
        if self.typ == 'first':
            return bug

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
            'bug_type': 'defect',
            'include_fields': fields,
            'resolution': '---',
            'f1': 'priority',
            'o1': 'equals',
            'v1': '--',
        }
        self.date = lmdutils.get_date_ymd(date)
        first = self.date - relativedelta(days=self.lookup_first * 7)
        second = self.date - relativedelta(days=self.lookup_second * 7)
        if self.typ == 'first':
            # TODO: change this when https://bugzilla.mozilla.org/1543984 will be fixed
            # Here we have to get bugs where product/component have been set (bug has been triaged)
            # between 4 and 2 weeks
            # If the product/component never changed after bug creation, we need to get them too
            # (second < p < first && c < first) ||
            # (second < c < first && p < first) ||
            # ((second < creation < first) && pc never changed)
            params.update(
                {
                    'f2': 'flagtypes.name',
                    'o2': 'notequals',
                    'v2': 'needinfo?',
                    'j3': 'OR',
                    'f3': 'OP',
                    'j4': 'AND',
                    'f4': 'OP',
                    'n5': 1,  # we use a negation here to be sure that no change after first
                    'f5': 'product',
                    'o5': 'changedafter',
                    'v5': first,
                    'f6': 'product',  # here the bug has changed
                    'o6': 'changedafter',
                    'v6': second,
                    'n7': 1,
                    'f7': 'component',
                    'o7': 'changedafter',
                    'v7': first,
                    'f8': 'CP',
                    'j9': 'AND',
                    'f9': 'OP',
                    'n10': 1,
                    'f10': 'component',
                    'o10': 'changedafter',
                    'v10': first,
                    'f11': 'component',
                    'o11': 'changedafter',
                    'v11': second,
                    'n12': 1,
                    'f12': 'product',
                    'o12': 'changedafter',
                    'v12': first,
                    'f13': 'CP',
                    'j14': 'AND',
                    'f14': 'OP',
                    'f15': 'creation_ts',
                    'o15': 'lessthaneq',
                    'v15': first,
                    'f16': 'creation_ts',
                    'o16': 'greaterthan',
                    'v16': second,
                    'n17': 1,
                    'f17': 'product',
                    'o17': 'changedafter',
                    'v17': '1970-01-01',
                    'n18': 1,
                    'f18': 'component',
                    'o18': 'changedafter',
                    'v18': '1970-01-01',
                    'f19': 'CP',
                    'f20': 'CP',
                }
            )
        else:
            params.update(
                {
                    'j2': 'OR',
                    'f2': 'OP',
                    'j3': 'AND',
                    'f3': 'OP',
                    'f4': 'product',
                    'o4': 'changedbefore',
                    'v4': second,
                    'n5': 1,
                    'f5': 'product',
                    'o5': 'changedafter',
                    'v5': second,
                    'f6': 'CP',
                    'j7': 'AND',
                    'f7': 'OP',
                    'f8': 'component',
                    'o8': 'changedbefore',
                    'v8': second,
                    'n9': 1,
                    'f9': 'component',
                    'o9': 'changedafter',
                    'v9': second,
                    'f10': 'CP',
                    'j11': 'AND',
                    'f11': 'OP',
                    'f12': 'creation_ts',
                    'o12': 'lessthaneq',
                    'v12': second,
                    'n13': 1,
                    'f13': 'product',
                    'o13': 'changedafter',
                    'v13': '1970-01-01',
                    'n14': 1,
                    'f14': 'component',
                    'o14': 'changedafter',
                    'v14': '1970-01-01',
                    'f15': 'CP',
                    'f16': 'CP',
                }
            )

        return params


if __name__ == '__main__':
    NoPriority('first').run()
    NoPriority('second').run()
