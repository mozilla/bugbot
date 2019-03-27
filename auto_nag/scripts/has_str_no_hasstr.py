# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
import re
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


STR = re.compile(r'^(?:Step[s]? to reproduce|STR|Step[s]?)[ \t]*:', re.I | re.MULTILINE)


class HasStrNoHasstr(BzCleaner):
    def __init__(self):
        super(HasStrNoHasstr, self).__init__()

    def description(self):
        return (
            'Get the bugs with no has_str and a "Steps to reproduce" in first comment'
        )

    def name(self):
        return 'has-str-no-hasstr'

    def template(self):
        return 'has_str_no_hasstr.html'

    def subject(self):
        return 'Bugs with no has_str and str in the first comment'

    def get_autofix_change(self):
        return {'cf_has_str': 'yes'}

    def get_bugs_with_str(self, bugs):
        def comment_handler(bug, bugid, data):
            text = bug['comments'][0]['text']
            if STR.search(text):
                bugid = str(bugid)
                data.add(bugid)

        bugids = list(bugs.keys())
        data = set()

        Bugzilla(
            bugids=bugids,
            commenthandler=comment_handler,
            commentdata=data,
            comment_include_fields=['text'],
        ).get_data().wait()

        return data

    def get_bz_params(self, date):
        tomorrow = lmdutils.get_date('tomorrow')
        start_date, _ = self.get_dates(date)
        fields = ['creator']
        params = {
            'include_fields': fields,
            'resolution': '---',
            'f1': 'longdesc',
            'o1': 'regexp',
            'v1': '([[:<:]]{}[[:>:]])|([[:<:]]{}?[[:>:]])|({}?[ \t]+{}[ \t]+{})[ \t]*:'.format(
                *map(utils.bz_ignore_case, ('str', 'steps', 'steps', 'to', 'reproduce'))
            ),
            'f2': 'cf_has_str',
            'o2': 'equals',
            'v2': '---',
            'n3': 1,
            'f3': 'cf_has_str',
            'o3': 'changedbefore',
            'v3': tomorrow,
            'f4': 'creation_ts',
            'o4': 'greaterthan',
            'v4': start_date,
            'f5': 'keywords',
            'o5': 'notsubstring',
            'v5': 'testcase-wanted',
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(HasStrNoHasstr, self).get_bugs(date=date, bug_ids=bug_ids)
        with_str = self.get_bugs_with_str(bugs)

        useless = set(bugs.keys()) - with_str
        for bug in useless:
            del bugs[bug]

        return bugs


if __name__ == '__main__':
    HasStrNoHasstr().run()
