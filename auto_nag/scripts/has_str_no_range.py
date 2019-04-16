# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
from auto_nag.bzcleaner import BzCleaner
from auto_nag.people import People


class HasSTRNoRange(BzCleaner):
    def __init__(self):
        super(HasSTRNoRange, self).__init__()
        self.people = People()
        self.autofix_reporters = {}

    def description(self):
        return 'Bugs with STR and no regression range'

    def get_autofix_change(self):
        return self.autofix_reporters

    def get_bugs_with_no_history(self, bugs):
        # The idea here is to only ask for regression window when only the bot
        # or the assignee contributed to the bug
        # bot = utils.get_config('common', 'bot_bz_mail')[0]

        def history_handler(bug, data):
            bugid = str(bug['id'])
            no_hist = True
            if bug['history']:
                bug_data = data[bugid]
                who = {bug_data['creator']}
                for h in bug['history']:
                    if h['who'] not in who:
                        no_hist = False
                        break
            data[bugid]['no_history'] = no_hist

        bugids = list(bugs.keys())
        Bugzilla(
            bugids=bugids, historyhandler=history_handler, historydata=bugs
        ).get_data().wait()

        res = {}
        for bugid, bug in bugs.items():
            if bug['no_history']:
                res[bugid] = bug
                if bug['regression']:
                    self.autofix_reporters[bugid] = {
                        'comment': {
                            'body': ':{}, could you try to find a regression range in using for example [mozregression](https://wiki.mozilla.org/Auto-tools/Projects/Mozregression)?'.format(
                                bug['nick']
                            )
                        }
                    }
                    if not bug['regwindow']:
                        self.autofix_reporters[bugid]['keywords'] = {
                            'add': ['regressionwindow-wanted']
                        }
                else:
                    self.autofix_reporters[bugid] = {
                        'comment': {
                            'body': ':{}, if you think that\'s a regression, then could you try to find a regression range in using for example [mozregression](https://wiki.mozilla.org/Auto-tools/Projects/Mozregression)?'.format(
                                bug['nick']
                            )
                        }
                    }
        return res

    def handle_bug(self, bug, data):
        bugid = str(bug['id'])
        creator = bug['creator']
        nick = bug['creator_detail']['nick']
        reg = 'regression' in bug['keywords']
        win = 'regressionwindow-wanted' in bug['keywords']

        data[bugid] = {
            'creator': creator,
            'nick': nick,
            'regression': reg,
            'regwindow': win,
        }

        return bug

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        fields = ['creator', 'keywords']
        params = {
            'include_fields': fields,
            'resolution': '---',
            'f1': 'creation_ts',
            'o1': 'greaterthan',
            'v1': start_date,
            'f2': 'cf_has_regression_range',
            'o2': 'equals',
            'v2': '---',
            'n3': 1,
            'f3': 'cf_has_regression_range',
            'o3': 'changedafter',
            'v3': start_date,
            'f4': 'cf_has_str',
            'o4': 'equals',
            'v4': 'yes',
            'n5': 1,
            'f5': 'longdesc',
            'o5': 'casesubstring',
            'v5': 'could you try to find a regression range in using for example [mozregression]',
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(HasSTRNoRange, self).get_bugs(date=date, bug_ids=bug_ids)
        bugs = self.get_bugs_with_no_history(bugs)

        return bugs


if __name__ == '__main__':
    HasSTRNoRange().run()
