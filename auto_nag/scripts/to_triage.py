# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import utils as lmdutils
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils
from auto_nag.escalation import Escalation
from auto_nag.nag_me import Nag
from auto_nag.round_robin import RoundRobin


class ToTriage(BzCleaner, Nag):
    def __init__(self):
        super(ToTriage, self).__init__()
        self.escalation = Escalation(self.people, data=self.get_config('escalation'))
        self.round_robin = RoundRobin(
            people=self.people, teams=self.get_config('teams', [])
        )
        self.components = self.round_robin.get_components()

    def description(self):
        return 'Bugs to triage'

    def nag_template(self):
        return self.template()

    def has_default_product(self):
        return False

    def has_product_component(self):
        return True

    def ignore_meta(self):
        return True

    def columns(self):
        return ['component', 'id', 'summary', 'type']

    def columns_nag(self):
        return self.columns()

    def handle_bug(self, bug, data):
        bugid = str(bug['id'])
        data[bugid] = {'type': bug['type']}
        return bug

    def set_people_to_nag(self, bug, buginfo):
        priority = 'default'
        if not self.filter_bug(priority):
            return None

        owner, _ = self.round_robin.get(bug, self.date)
        real_owner = bug['triage_owner']
        buginfo['type'] = bug['type']
        self.add_triage_owner(owner, real_owner=real_owner)
        if not self.add(owner, buginfo, priority=priority):
            self.add_no_manager(buginfo['id'])
        return bug

    def get_bz_params(self, date):
        self.date = lmdutils.get_date_ymd(date)
        prods, comps = utils.get_products_components(self.components)
        fields = ['triage_owner', 'type']
        params = {
            'include_fields': fields,
            'product': list(prods),
            'component': list(comps),
            'resolution': '---',
            'f1': 'priority',
            'o1': 'equals',
            'v1': '--',
            'f2': 'flagtypes.name',
            'o2': 'notequals',
            'v2': 'needinfo?',
        }

        return params


if __name__ == '__main__':
    ToTriage().run()
