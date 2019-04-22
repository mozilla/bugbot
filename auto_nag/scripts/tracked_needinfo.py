# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils
from auto_nag.nag_me import Nag


class TrackedNeedinfo(BzCleaner, Nag):
    def __init__(self, channel):
        super(TrackedNeedinfo, self).__init__()
        self.channel = channel
        self.versions = utils.get_checked_versions()
        self.version = self.versions[channel] if self.versions else None

    def description(self):
        return 'Bugs which are tracked or nominated for tracking with needinfo? in {} {} '.format(
            self.channel, self.version
        )

    def has_last_comment_time(self):
        return True

    def has_assignee(self):
        return True

    def has_needinfo(self):
        return True

    def has_default_products(self):
        return False

    def get_extra_for_template(self):
        return {'channel': self.channel, 'version': self.version}

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def has_enough_data(self):
        return bool(self.versions)

    def columns(self):
        return ['id', 'summary', 'needinfos', 'assignee', 'last_comment']

    def columns_nag(self):
        return self.columns()

    def set_people_to_nag(self, bug, buginfo):
        priority = self.get_priority(bug)
        if not self.filter_bug(priority):
            return None

        has_manager = False
        for flag in utils.get_needinfo(bug, days=1):
            requestee = flag.get('requestee', '')
            if requestee:
                if self.add(requestee, buginfo, priority=priority):
                    has_manager = True

        if not has_manager:
            self.add_no_manager(buginfo['id'])

        return bug

    def get_bz_params(self, date):
        status = utils.get_flag(self.version, 'status', self.channel)
        self.tracking = utils.get_flag(self.version, 'tracking', self.channel)
        fields = ['assigned_to', 'flags', self.tracking]
        params = {
            'include_fields': fields,
            'resolution': '---',
            'bug_status': ','.join(['UNCONFIRMED', 'NEW', 'ASSIGNED', 'REOPENED']),
            'f1': self.tracking,
            'o1': 'anywords',
            'v1': ','.join(['+', '?', 'blocking']),
            'f2': 'flagtypes.name',
            'o2': 'equals',
            'v2': 'needinfo?',
            'f3': status,
            'o3': 'equals',
            'v3': 'affected',
            'f4': self.tracking,
            'o4': 'changedbefore',
            'v4': '-1d',
            'n5': 1,
            'f5': self.tracking,
            'o5': 'changedafter',
            'v5': '-1d',
        }

        return params


if __name__ == '__main__':
    TrackedNeedinfo('beta').run()
    TrackedNeedinfo('central').run()
    TrackedNeedinfo('esr').run()
