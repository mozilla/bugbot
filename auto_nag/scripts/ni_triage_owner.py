# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class NiTriageOwner(BzCleaner):
    def __init__(self, mail_owner, nick_owner, max_ni):
        super(NiTriageOwner, self).__init__()
        self.nweeks = utils.get_config(self.name(), 'number_of_weeks', 2)
        self.mail = mail_owner
        self.nick = nick_owner
        self.max_ni = max_ni

    def description(self):
        return 'Get bugs an empty priority flag and no activity for {} weeks'.format(
            self.nweeks
        )

    def name(self):
        return 'ni-triage-owner'

    def template(self):
        return 'ni_triage_owner.html'

    def needinfo_template(self):
        return 'ni_triage_owner_comment.txt'

    def subject(self):
        return 'Bugs with no priority and no activity for {} weeks'.format(self.nweeks)

    def get_extra_for_template(self):
        return {'nweeks': self.nweeks}

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def ignore_bug_summary(self):
        return False

    def get_max_ni(self):
        return self.max_ni

    def get_mail_to_auto_ni(self, bug):
        # when triage_owner and triage_owner_detail will be available
        # in Bugzilla, then we could use that stuff and remove "else".
        if False and 'triage_owner' in bug:
            mail = bug['triage_owner']
            nick = bug['triage_owner_detail']['nickname']
        else:
            mail = self.mail
            nick = self.nick

        return {'mail': mail, 'nickname': nick}

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)
        fields = ['product', 'component', 'triage_owner']
        params = {
            'triage_owner': self.mail,
            'include_fields': fields,
            'resolution': '---',
            'f1': 'priority',
            'o1': 'equals',
            'v1': '--',
            'f2': 'days_elapsed',
            'o2': 'greaterthan',
            'v2': self.nweeks * 7,
            'f3': 'creation_ts',
            'o3': 'greaterthan',
            'v3': start_date,
        }

        return params


if __name__ == '__main__':
    owners = utils.get_config('ni-triage-owner', 'owners', {})
    for mail, info in owners.items():
        NiTriageOwner(mail, info['nick'], int(info['max_ni'])).run()
