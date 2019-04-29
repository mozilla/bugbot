# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import dateutil.parser
from libmozdata.bugzilla import Bugzilla
from auto_nag.bzcleaner import BzCleaner


class ProdCompChangedWithPriority(BzCleaner):
    def __init__(self):
        super(ProdCompChangedWithPriority, self).__init__()

    def description(self):
        return 'Bugs with a priority set before product::component changed'

    def filter_bugs(self, bugs):
        def history_handler(bug, data):
            priority_date = None
            prod_comp_date = None
            priority_who = None
            prod_comp_who = None
            for h in bug['history']:
                for change in h['changes']:
                    if change['field_name'] == 'priority':
                        priority_date = dateutil.parser.parse(h['when'])
                        priority_who = h['who']
                    elif change['field_name'] in {'product', 'component'}:
                        prod_comp_date = dateutil.parser.parse(h['when'])
                        prod_comp_who = h['who']
            if (
                priority_date is None
                or prod_comp_date is None
                or priority_date >= prod_comp_date
                or priority_who == prod_comp_who
            ):
                del data[str(bug['id'])]

        bugids = list(bugs.keys())
        Bugzilla(
            bugids=bugids, historyhandler=history_handler, historydata=bugs
        ).get_data().wait()

        return bugs

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)
        params = {
            'bug_status': '__open__',
            'f1': 'priority',
            'o1': 'nowords',
            'v1': '--,P1,P2',
            'j2': 'OR',
            'f2': 'OP',
            'f3': 'product',
            'o3': 'changedafter',
            'v3': '1970-01-01',
            'f4': 'component',
            'o4': 'changedafter',
            'v4': '1970-01-01',
            'f5': 'CP',
            'f6': 'creation_ts',
            'o6': 'greaterthan',
            'v6': start_date,
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(ProdCompChangedWithPriority, self).get_bugs(
            date=date, bug_ids=bug_ids
        )
        bugs = self.filter_bugs(bugs)

        return bugs

    def get_autofix_change(self):
        doc = self.get_documentation()
        return {
            'comment': {
                'body': 'The product::component changed after the priority has been set so reset the priority.\n{}'.format(
                    doc
                )
            },
            'priority': '--',
        }


if __name__ == '__main__':
    ProdCompChangedWithPriority().run()
