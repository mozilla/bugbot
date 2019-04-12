# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class DupemeWhiteboardKeyword(BzCleaner):
    def __init__(self):
        super(DupemeWhiteboardKeyword, self).__init__()
        self.autofix_whiteboard = {}

    def description(self):
        return 'Bugs with dupeme in the whiteboard instead of keyword'

    def get_autofix_change(self):
        return self.autofix_whiteboard

    def handle_bug(self, bug, data):
        bugid = str(bug['id'])
        whiteboard = bug['whiteboard']
        wb = utils.ireplace("[dupeme]", "", whiteboard)
        self.autofix_whiteboard[bugid] = {'whiteboard': wb,
                                          'keywords': {'add': ['dupeme']}}
        return bug

    def get_bz_params(self, date):
        days_lookup = self.get_config('days_lookup', default=180)
        fields = ['whiteboard']
        return {
            'include_fields': fields,
            'resolution': ['---'],
            'status_whiteboard_type': 'allwordssubstr',
            'status_whiteboard': '[dupeme]',
            'f1': 'days_elapsed',
            'o1': 'lessthan',
            'v1': days_lookup,
        }


if __name__ == '__main__':
    DupemeWhiteboardKeyword().run()
