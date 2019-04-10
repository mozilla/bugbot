# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import release_calendar as rc
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class P2MergeDay(BzCleaner):
    def __init__(self):
        super(P2MergeDay, self).__init__()

    def must_run(self, date):
        cal = rc.get_calendar()
        for c in cal:
            if date == c['merge']:
                return True
        return False

    def description(self):
        return 'P2 bugs with an assignee on merge day'

    def has_product_component(self):
        return True

    def ignore_meta(self):
        return True

    def columns(self):
        return ['component', 'id', 'summary']

    def handle_bug(self, bug, data):
        # check if the product::component is in the list
        if not utils.check_product_component(self.components, bug):
            return None
        return bug

    def get_bz_params(self, date):
        self.components = utils.get_config('workflow', 'components')
        params = {
            'component': utils.get_components(self.components),
            'resolution': '---',
            'f1': 'priority',
            'o1': 'equals',
            'v1': 'P2',
        }

        utils.get_empty_assignees(params)

        return params

    def get_autofix_change(self):
        return {
            'comment': {
                'body': 'Set the priority to P1 since today is the merge day.\nSee [How Do You Triage](https://mozilla.github.io/bug-handling/triage-bugzilla#how-do-you-triage) for more information.'
            },
            'priority': 'P1',
        }


if __name__ == '__main__':
    P2MergeDay().run()
