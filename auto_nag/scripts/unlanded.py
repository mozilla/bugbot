# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.common import get_current_versions
from auto_nag import utils
from auto_nag.nag_me import Nag


class Unlanded(BzCleaner, Nag):
    def __init__(self, channel):
        super(Unlanded, self).__init__()
        self.channel = channel

    def description(self):
        return 'Get bugs with unlanded {} uplifts'.format(self.channel)

    def name(self):
        return 'unlanded-' + self.channel

    def template(self):
        return 'unlanded.html'

    def nag_template(self):
        return 'unlanded_nag.html'

    def subject(self):
        return self.description()

    def must_run(self, date):
        weekday = date.weekday()
        # no nagging the week-end
        return weekday <= 4

    def ignore_bug_summary(self):
        return False

    def has_last_comment_time(self):
        return True

    def set_people_to_nag(self, bug):
        assignee = bug['assigned_to']
        bugid = str(bug['id'])
        real = bug['assigned_to_detail']['real_name']
        bug_data = {'id': bugid, 'summary': self.get_summary(bug), 'to': assignee}
        self.add_assignee(bugid, real)
        if not self.add(assignee, bug_data):
            self.add_no_manager(bugid)
        return bug

    def get_bz_params(self, date):
        version = get_current_versions()[self.channel]
        if self.channel == 'esr':
            bug_ids = utils.get_report_bugs(self.channel + version)
        else:
            bug_ids = utils.get_report_bugs(self.channel)
        status = utils.get_flag(version, 'status', self.channel)
        tracking = utils.get_flag(version, 'tracking', self.channel)
        fields = ['assigned_to']
        params = {
            'include_fields': fields,
            'bug_id': ','.join(bug_ids),
            'f1': status,
            'o1': 'nowordssubstr',
            'v1': ','.join(['unaffected', 'fixed', 'verified', 'wontfix', 'disabled']),
            'f2': tracking,
            'o2': 'equals',
            'v2': '+',
            'f3': 'status_whiteboard',
            'o3': 'notsubstring',
            'v3': '[no-nag]',
        }

        return params


if __name__ == '__main__':
    Unlanded('beta').run()
    Unlanded('esr').run()
