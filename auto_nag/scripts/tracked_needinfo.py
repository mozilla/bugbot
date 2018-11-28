# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.common import get_current_versions
from auto_nag import utils
from auto_nag.nag_me import Nag


class TrackedNeedinfo(BzCleaner, Nag):
    def __init__(self, channel):
        super(TrackedNeedinfo, self).__init__()
        self.channel = channel
        self.version = get_current_versions()[channel]

    def description(self):
        return 'Get bugs which are tracked or nominated for tracking with needinfo? in {} {} '.format(
            self.channel, self.version
        )

    def name(self):
        return 'tracked-needinfo'

    def template(self):
        return 'tracked_needinfo.html'

    def nag_template(self):
        return 'tracked_needinfo_nag.html'

    def subject(self):
        return 'Bugs which are tracked or nominated for tracking with Need-Info? in {} {} '.format(
            self.channel, self.version
        )

    def ignore_bug_summary(self):
        return False

    def has_last_comment_time(self):
        return True

    def has_assignee(self):
        return True

    def has_needinfo(self):
        return True

    def has_default_products(self):
        return False

    def must_run(self, date):
        weekday = date.weekday()
        # no nagging the week-end
        return weekday <= 4

    def get_extra_for_template(self):
        return {'channel': self.channel, 'version': self.version}

    def get_extra_for_nag_template(self):
        return {
            'channel': self.channel,
            'version': self.version,
            'needinfos': self.get_needinfo_for_template(),
            'assignees': self.assignees,
        }

    def set_people_to_nag(self, bug):
        bugid = str(bug['id'])
        has_manager = False
        for flag in utils.get_needinfo(bug):
            requestee = flag['requestee']
            bug_data = {'id': bugid, 'summary': self.get_summary(bug), 'to': requestee}
            if self.add(requestee, bug_data):
                has_manager = True

        if not has_manager:
            self.add_no_manager(bugid)

        return bug

    def get_bz_params(self, date):
        status = utils.get_flag(self.version, 'status', self.channel)
        tracking = utils.get_flag(self.version, 'tracking', self.channel)
        fields = ['assigned_to', 'flags']
        params = {
            'include_fields': fields,
            'resolution': '---',
            'bug_status': ','.join(['UNCONFIRMED', 'NEW', 'ASSIGNED', 'REOPENED']),
            'f1': tracking,
            'o1': 'anywords',
            'v1': '+,?',
            'f2': 'flagtypes.name',
            'o2': 'equals',
            'v2': 'needinfo?',
            'f3': status,
            'o3': 'nowordssubstr',
            'v3': ','.join(['wontfix', 'fixed', 'disabled', 'verified', 'unaffected']),
        }

        return params


if __name__ == '__main__':
    TrackedNeedinfo('beta').run()
    TrackedNeedinfo('central').run()
    TrackedNeedinfo('esr').run()
