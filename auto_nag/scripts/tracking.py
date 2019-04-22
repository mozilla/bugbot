# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils
from auto_nag.nag_me import Nag


class Tracking(BzCleaner, Nag):
    def __init__(self, channel, untouched):
        super(Tracking, self).__init__()
        self.channel = channel
        self.untouched = untouched
        self.assignees = {}
        self.versions = utils.get_checked_versions()
        self.version = self.versions[self.channel] if self.versions else None

    def description(self):
        if self.untouched:
            return 'Bugs which are tracked in {} {} and untouched in the last 3 days'.format(
                self.channel, self.version
            )

        return 'Bugs which are tracked in {} {}'.format(self.channel, self.version)

    def name(self):
        return 'tracking' + ('_untouched' if self.untouched else '')

    def template(self):
        return 'tracking.html'

    def nag_template(self):
        return 'tracking_nag.html'

    def has_last_comment_time(self):
        return True

    def has_default_products(self):
        return False

    def has_needinfo(self):
        return True

    def has_assignee(self):
        return True

    def get_extra_for_template(self):
        return {
            'channel': self.channel,
            'version': self.version,
            'untouched': self.untouched,
            'next_release': (utils.get_next_release_date() - self.nag_date).days,
        }

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def has_enough_data(self):
        return bool(self.versions)

    def columns(self):
        return ['id', 'summary', 'needinfos', 'assignee', 'last_comment']

    def columns_nag(self):
        return ['id', 'summary', 'needinfos', 'To', 'last_comment']

    def set_people_to_nag(self, bug, buginfo):
        priority = self.get_priority(bug)
        if not self.filter_bug(priority):
            return None

        assignee = bug['assigned_to']
        real = bug['assigned_to_detail']['real_name']
        buginfo['to'] = assignee
        buginfo['To'] = real

        if not self.add(assignee, buginfo, priority=priority):
            self.add_no_manager(buginfo['id'])

        return bug

    def get_bz_params(self, date):
        v = self.versions[self.channel]
        status = utils.get_flag(v, 'status', self.channel)
        self.tracking = utils.get_flag(v, 'tracking', self.channel)
        tracking_value = (
            '+,blocking' if self.channel != 'esr' else self.versions['beta'] + '+'
        )
        fields = [self.tracking]
        params = {
            'include_fields': fields,
            'f1': self.tracking,
            'o1': 'anywords',
            'v1': tracking_value,
            'f2': status,
            'o2': 'nowordssubstr',
            'v2': ','.join(['wontfix', 'fixed', 'disabled', 'verified', 'unaffected']),
            'f3': self.tracking,
            'o3': 'changedbefore',
            'v3': '-1d',
            'n4': 1,
            'f4': self.tracking,
            'o4': 'changedafter',
            'v4': '-1d',
        }

        if self.channel == 'central':
            tracking = utils.get_flag(self.versions['beta'], 'tracking', 'beta')
            params.update({'f5': tracking, 'o5': 'nowordssubstr', 'v5': '+,blocking'})
        elif self.channel != 'esr':
            approval = utils.get_flag(v, 'approval', self.channel)
            params.update(
                {'f5': 'flagtypes.name', 'o5': 'notsubstring', 'v5': approval + '?'}
            )

        if self.untouched:
            params.update({'f6': 'days_elapsed', 'o6': 'greaterthan', 'v6': 3})

        return params


if __name__ == '__main__':
    Tracking('beta', False).run()
    Tracking('beta', True).run()
    Tracking('central', False).run()
    Tracking('central', True).run()
    Tracking('esr', False).run()
