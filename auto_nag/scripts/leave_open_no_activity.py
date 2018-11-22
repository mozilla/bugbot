# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.people import People
from auto_nag import utils


class LeaveOpenNoActivity(BzCleaner):
    def __init__(self):
        super(LeaveOpenNoActivity, self).__init__()
        self.people = People()
        self.nmonths = utils.get_config(self.name(), 'months_lookup')
        self.max_ni = utils.get_config(self.name(), 'max_ni')

    def description(self):
        return 'Get bugs with leave-open keyword and no activity for the last {} months'.format(
            self.nmonths
        )

    def name(self):
        return 'leave-open-no-activity'

    def template(self):
        return 'leave_open_no_activity.html'

    def needinfo_template(self):
        return 'ni_for_leave_open_no_activity_comment.txt'

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def ignore_bug_summary(self):
        return False

    def subject(self):
        return 'Bugs with leave-open keyword and no activity for the last {} months'.format(
            self.nmonths
        )

    def get_extra_for_template(self):
        return {'nmonths': self.nmonths}

    def get_max_ni(self):
        return self.max_ni

    def get_mail_to_auto_ni(self, bug):
        for f in ['assigned_to', 'triage_owner']:
            person = bug.get(f, '')
            if person and self.people.is_mozilla(person):
                return {'mail': person, 'nickname': bug[f + '_detail']['nick']}

        return None

    def get_bz_params(self, date):
        fields = ['assigned_to', 'triage_owner']
        params = {
            'include_fields': fields,
            'resolution': '---',
            'f1': 'keywords',
            'o1': 'casesubstring',
            'v1': 'leave-open',
            'f2': 'days_elapsed',
            'o2': 'greaterthan',
            'v2': self.nmonths * 30,
        }

        return params


if __name__ == '__main__':
    LeaveOpenNoActivity().run()
