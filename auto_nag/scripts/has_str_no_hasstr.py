# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
import re
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


STR = re.compile(r'^(?:Step[s]? to reproduce|STR|Step[s]?)[ \t]*:', re.I | re.MULTILINE)


class HasStrNoHasstr(BzCleaner):
    def __init__(self):
        super(HasStrNoHasstr, self).__init__()
        self.autofix_hasstr = {}

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

    def set_autofix(self, bugs, with_str):
        for bugid, one_comment in with_str.items():
            bug = bugs[bugid]
            if one_comment:
                # we restrict this autofix to bugs with only one comment and no history
                # to avoid a maybe inappropriate comment in a chat.
                nick = bug['nick']
                self.autofix_hasstr[bugid] = {
                    'cf_has_str': 'yes',
                    'comment': {
                        'body': ':{}, if you think that\'s a regression, then could try to find a regression range in using for example [mozregression](https://wiki.mozilla.org/Auto-tools/Projects/Mozregression)?'.format(
                            nick
                        )
                    },
                }
            else:
                self.autofix_hasstr[bugid] = {'cf_has_str': 'yes'}

    def has_product_component(self):
        return True

    def get_autofix_change(self):
        return self.autofix_hasstr

    def handle_bug(self, bug, data):
        bugid = str(bug['id'])
        data[bugid] = {'nick': bug['creator_detail']['nick']}
        return bug

    def get_bugs_with_str(self, bugs):
        def comment_handler(bug, bugid, data):
            text = bug['comments'][0]['text']
            if STR.search(text):
                bugid = str(bugid)
                data[bugid] = len(bug['comments']) == 1

        bugids = list(bugs.keys())
        data = {}

        Bugzilla(
            bugids=bugids,
            commenthandler=comment_handler,
            commentdata=data,
            comment_include_fields=['text'],
        ).get_data().wait()

        return data

    def get_bugs_with_no_history(self, bugs):
        def history_handler(bug, data):
            if not bug['history']:
                bugid = str(bug['id'])
                data.add(bugid)

        bugids = [bugid for bugid, one_comment in bugs.items() if one_comment]
        data = set()

        Bugzilla(
            bugids=bugids, historyhandler=history_handler, historydata=data
        ).get_data().wait()

        for bugid in bugs.keys():
            if bugid not in data:
                bugs[bugid] = False

    def get_bz_params(self, date):
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
            'f3': 'creation_ts',
            'o3': 'greaterthan',
            'v3': start_date,
            'f4': 'keywords',
            'o4': 'notsubstring',
            'v4': 'testcase-wanted',
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(HasStrNoHasstr, self).get_bugs(date=date, bug_ids=bug_ids)
        with_str = self.get_bugs_with_str(bugs)
        self.get_bugs_with_no_history(with_str)

        useless = set(bugs.keys()) - set(with_str.keys())
        for bug in useless:
            del bugs[bug]

        self.set_autofix(bugs, with_str)

        return bugs


if __name__ == '__main__':
    HasStrNoHasstr().run()
