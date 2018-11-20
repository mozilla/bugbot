# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils
from auto_nag.nag_me import Nag


class NiFromManager(BzCleaner, Nag):
    def __init__(self):
        super(NiFromManager, self).__init__()
        self.nweeks = utils.get_config(self.name(), 'number_of_weeks', 1)
        self.vip = self.get_people().get_rm_or_directors()
        self.white_list = utils.get_config(self.name(), 'white-list', [])
        self.black_list = utils.get_config(self.name(), 'black-list', [])

    def description(self):
        return 'Get bugs with a ni from a director or a release manager with no activity for the last {} {}'.format(
            self.nweeks, utils.plural('week', self.nweeks)
        )

    def name(self):
        return 'ni-from-manager'

    def template(self):
        return 'ni_from_manager.html'

    def nag_template(self):
        return 'ni_from_manager_nag.html'

    def subject(self):
        return 'Bugs with a ni from a director or a release manager and no activity for the last {} {}'.format(
            self.nweeks, utils.plural('week', self.nweeks)
        )

    def get_extra_for_template(self):
        return {'nweeks': self.nweeks}

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def ignore_bug_summary(self):
        return False

    def has_last_comment_time(self):
        return True

    def has_needinfo(self):
        return True

    def set_people_to_nag(self, bug):
        bugid = str(bug['id'])
        has_manager = False
        for flag in bug['flags']:
            if (
                flag.get('name', '') == 'needinfo'
                and flag['status'] == '?'
                and flag['setter'] in self.vip
            ):
                requestee = flag['requestee']
                if self.is_under(requestee):
                    bug_data = {
                        'id': bugid,
                        'summary': self.get_summary(bug),
                        'to': requestee,
                        'from': self.get_people().get_moz_name(flag['setter']),
                    }
                    if self.add(requestee, bug_data):
                        has_manager = True

        if not has_manager:
            self.add_no_manager(bugid)

        return bug

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)
        fields = ['flags']
        params = {
            'include_fields': fields,
            'resolution': '---',
            'f1': 'days_elapsed',
            'o1': 'greaterthan',
            'v1': self.nweeks * 7,
            'f2': 'flagtypes.name',
            'o2': 'casesubstring',
            'v2': 'needinfo?',
            'f3': 'setters.login_name',
            'o3': 'anyexact',
            # there are not so much vip so the query shouldn't be too big
            'v3': ','.join(self.vip),
            'f4': 'creation_ts',
            'o4': 'greaterthan',
            'v4': start_date,
        }

        return params


if __name__ == '__main__':
    NiFromManager().run()
