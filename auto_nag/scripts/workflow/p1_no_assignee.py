# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils
from auto_nag.escalation import Escalation, NoActivityDays
from auto_nag.nag_me import Nag


class P1NoAssignee(BzCleaner, Nag):
    def __init__(self):
        super(P1NoAssignee, self).__init__()
        self.escalation = Escalation(
            self.people,
            data=utils.get_config('workflow_' + self.name(), 'escalation'),
            blacklist=utils.get_config('workflow', 'supervisor_blacklist', []),
        )

    def description(self):
        return 'P1 Bugs, no assignee and no activity for {} days'.format(self.ndays)

    def nag_template(self):
        return self.template()

    def get_extra_for_template(self):
        return {'ndays': self.ndays}

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def ignore_meta(self):
        return True

    def has_last_comment_time(self):
        return True

    def has_product_component(self):
        return True

    def columns(self):
        return ['component', 'id', 'summary', 'last_comment']

    def get_mail_to_auto_ni(self, bug):
        # Avoid to ni everyday...
        if self.has_bot_set_ni(bug):
            return None

        mail = bug['triage_owner']
        nick = bug['triage_owner_detail']['nick']
        return {'mail': mail, 'nickname': nick}

    def set_people_to_nag(self, bug, buginfo):
        priority = 'high'
        if not self.filter_bug(priority):
            return None

        owner = bug['triage_owner']
        self.add_triage_owner(owner, utils.get_config('workflow', 'components'))
        if not self.add(owner, buginfo, priority=priority):
            self.add_no_manager(buginfo['id'])

        return bug

    def get_bz_params(self, date):
        self.ndays = NoActivityDays(self.name()).get(
            (utils.get_next_release_date() - self.nag_date).days
        )
        fields = ['triage_owner', 'flags']
        comps = utils.get_config('workflow', 'components')
        params = {
            'component': comps,
            'include_fields': fields,
            'resolution': '---',
            'f1': 'priority',
            'o1': 'equals',
            'v1': 'P1',
            'f2': 'days_elapsed',
            'o2': 'greaterthaneq',
            'v2': self.ndays,
        }

        utils.get_empty_assignees(params)

        return params


if __name__ == '__main__':
    P1NoAssignee().run()
