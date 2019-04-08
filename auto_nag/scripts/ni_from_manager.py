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
        return 'Bugs with a ni from a director or a release manager without activity for the last {} {}'.format(
            self.nweeks, utils.plural('week', self.nweeks)
        )

    def get_extra_for_template(self):
        return {'nweeks': self.nweeks}

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def has_last_comment_time(self):
        return True

    def has_needinfo(self):
        return True

    def columns(self):
        return ['id', 'summary', 'needinfos', 'last_comment']

    def columns_nag(self):
        return ['id', 'summary', 'to', 'from', 'last_comment']

    def get_priority(self, bug):
        return 'normal'

    def set_people_to_nag(self, bug, buginfo):
        priority = self.get_priority(bug)
        if not self.filter_bug(priority):
            return None

        has_manager = False
        accepted = False
        for flag in bug['flags']:
            if (
                flag.get('name', '') == 'needinfo'
                and flag['status'] == '?'
                and flag['setter'] in self.vip
            ):
                requestee = flag['requestee']
                if self.is_under(requestee):
                    accepted = True
                    buginfo['to'] = requestee
                    buginfo['from'] = self.get_people().get_moz_name(flag['setter'])
                    if self.add(requestee, buginfo):
                        has_manager = True

        if accepted and not has_manager:
            self.add_no_manager(buginfo['id'])

        return bug if accepted else None

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
