# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
from auto_nag.bzcleaner import BzCleaner


class WarnRegressedBy(BzCleaner):
    def __init__(self):
        super(WarnRegressedBy, self).__init__()
        self.regressions = {}
        self.threshold = self.get_config('threshold', 3)
        self.days = self.get_config('days_lookup', 14)

    def description(self):
        return 'Bugs with more than {} regressions reported in the last {} days'.format(
            self.threshold, self.days
        )

    def get_extra_for_template(self):
        return {'threshold': self.threshold, 'days': self.days}

    def handle_bug(self, bug, data):
        # since we use the bughandler for the second round we mustn't look at regressed_by stuff
        if self.regressions is None:
            return bug

        bugid = str(bug['id'])

        for reg_id in bug['regressed_by']:
            reg_id = str(reg_id)
            if reg_id not in self.regressions:
                self.regressions[reg_id] = [bugid]
            else:
                self.regressions[reg_id].append(bugid)

        return bug

    def to_warn(self):
        bugids = []
        for reg_id, bids in self.regressions.items():
            if len(bids) >= self.threshold:
                bugids.append(reg_id)

        fields = ['id', 'summary', 'groups']
        self.regressions = None
        data = {}
        Bugzilla(
            bugids=bugids,
            include_fields=fields,
            bughandler=self.bughandler,
            bugdata=data,
        ).get_data().wait()

        return data

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)
        fields = ['regressed_by']
        params = {
            'include_fields': fields,
            'bug_type': 'defect',
            'f1': 'regressed_by',
            'o1': 'isnotempty',
            'f2': 'creation_ts',
            'o2': 'greaterthan',
            'v2': start_date,
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(WarnRegressedBy, self).get_bugs(date=date, bug_ids=bug_ids)
        bugs = self.to_warn()

        return bugs


if __name__ == '__main__':
    WarnRegressedBy().run()
