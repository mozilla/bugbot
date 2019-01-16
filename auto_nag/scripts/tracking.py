# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.common import get_current_versions
from auto_nag import utils
from auto_nag.nag_me import Nag


class Tracking(BzCleaner, Nag):
    def __init__(self, channel, untouched):
        super(Tracking, self).__init__()
        self.channel = channel
        self.untouched = untouched
        self.assignees = {}
        self.versions = get_current_versions()
        self.version = self.versions[self.channel]

    def description(self):
        if self.untouched:
            return 'Get the tracked bugs in {} {} and untouched this week'.format(
                self.channel, self.version
            )

        return 'Get the tracked bugs in {} {}'.format(self.channel, self.version)

    def name(self):
        return 'tracking' + ('-untouched' if self.untouched else '')

    def template(self):
        return 'tracking.html'

    def nag_template(self):
        return 'tracking_nag.html'

    def subject(self):
        if self.untouched:
            return 'Bugs which are tracked in {} {} and untouched this week'.format(
                self.channel, self.version
            )

        return 'Bugs which are tracked in {} {}'.format(self.channel, self.version)

    def ignore_bug_summary(self):
        return False

    def has_last_comment_time(self):
        return True

    def has_default_products(self):
        return False

    def get_extra_for_template(self):
        return {
            'channel': self.channel,
            'version': self.version,
            'untouched': self.untouched,
        }

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def set_people_to_nag(self, bug):
        priority = self.get_priority(bug)
        if not self.filter_bug(priority):
            return None

        assignee = bug['assigned_to']
        bugid = str(bug['id'])
        real = bug['assigned_to_detail']['real_name']
        bug_data = {
            'id': bugid,
            'summary': self.get_summary(bug),
            'to': assignee,
            'To': real,
        }

        self.add_assignee(bugid, real)
        if not self.add(assignee, bug_data, priority=priority):
            self.add_no_manager(bugid)

        return bug

    def get_bz_params(self, date):
        v = self.versions[self.channel]
        status = utils.get_flag(v, 'status', self.channel)
        self.tracking = utils.get_flag(v, 'tracking', self.channel)
        tracking_value = (
            '+,blocking' if self.channel != 'esr' else self.versions['beta'] + '+'
        )
        fields = ['assigned_to', self.tracking]
        params = {
            'include_fields': fields,
            'f1': self.tracking,
            'o1': 'anywords',
            'v1': tracking_value,
            'f2': status,
            'o2': 'nowordssubstr',
            'v2': ','.join(['wontfix', 'fixed', 'disabled', 'verified', 'unaffected']),
        }

        if self.channel == 'central':
            tracking = utils.get_flag(self.versions['beta'], 'tracking', 'beta')
            params.update({'f3': tracking, 'o3': 'nowordssubstr', 'v3': '+,blocking'})
        elif self.channel != 'esr':
            approval = utils.get_flag(v, 'approval', self.channel)
            params.update(
                {'f3': 'flagtypes.name', 'o3': 'notsubstring', 'v3': approval + '?'}
            )

        if self.untouched:
            params.update({'f4': 'days_elapsed', 'o4': 'greaterthan', 'v4': 3})

        return params


if __name__ == '__main__':
    Tracking('beta', False).run()
    Tracking('beta', True).run()
    Tracking('central', False).run()
    Tracking('central', True).run()
    Tracking('esr', False).run()
