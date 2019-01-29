# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils
from auto_nag.escalation import Escalation, NoActivityDays
from auto_nag.nag_me import Nag


class P1NoActivity(BzCleaner, Nag):
    def __init__(self):
        super(P1NoActivity, self).__init__()
        self.escalation = Escalation(
            self.people, data=utils.get_config(self.name(), 'escalation')
        )

    def description(self):
        return 'Get bugs with priority P1 and no activity for few days'

    def name(self):
        return 'workflow-p1-no-activity'

    def template(self):
        return 'workflow_p1_no_activity.html'

    def nag_template(self):
        return 'workflow_p1_no_activity_nag.html'

    def subject(self):
        return 'Bugs with P1 and no activity for {} days'.format(self.ndays)

    def get_extra_for_template(self):
        return {'ndays': self.ndays}

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def ignore_bug_summary(self):
        return False

    def has_last_comment_time(self):
        return True

    def has_assignee(self):
        return True

    def set_people_to_nag(self, bug):
        priority = 'high'
        if not self.filter_bug(priority):
            return None

        bugid = str(bug['id'])
        owner = bug['triage_owner']
        assignee = bug['assigned_to']
        bug_data = {'id': bugid, 'summary': self.get_summary(bug)}
        if not self.add(assignee, bug_data, priority=priority, triage_owner=owner):
            self.add_no_manager(bugid)

        return bug

    def get_bz_params(self, date):
        self.ndays = NoActivityDays(self.name()).get(
            (utils.get_next_release_date() - self.nag_date).days
        )
        fields = ['triage_owner', 'assigned_to']
        params = {
            'product': 'Core',
            'include_fields': fields,
            'resolution': '---',
            'f1': 'component',
            'o1': 'casesubstring',
            'v1': 'Networking',
            'f2': 'priority',
            'o2': 'equals',
            'v2': 'P1',
            'f3': 'assigned_to',
            'o3': 'nowordssubstr',
            'v3': ','.join(utils.get_empty_assignees()),
            'f4': 'days_elapsed',
            'o4': 'greaterthaneq',
            'v4': self.ndays,
        }
        return params


if __name__ == '__main__':
    P1NoActivity().run()
