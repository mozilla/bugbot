# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils
from auto_nag.people import People


class NewbieWithNI(BzCleaner):
    def __init__(self):
        super(NewbieWithNI, self).__init__()
        self.people = People()
        self.ndays = utils.get_config(self.name(), 'number_of_days', 14)
        self.ncomments = utils.get_config(self.name(), 'number_of_comments', 2)
        self.autofix_reporters = {}

    def description(self):
        return 'Bugs where the reporter has a needinfo and no activity for the last {} weeks'.format(
            self.ndays
        )

    def get_extra_for_template(self):
        return {'ndays': self.ndays, 'ncomments': self.ncomments}

    def get_autofix_change(self):
        return self.autofix_reporters

    def set_autofix(self, bugs):
        for bugid, v in bugs.items():
            nick = v['creator_nick']
            self.autofix_reporters[bugid] = {
                'comment': {
                    'body': 'Closing as INCOMPLETE because no answer to the needinfo.\n:{}, feel free to reopen the bug if you\'ve more information to provide.'.format(
                        nick
                    )
                },
                'status': 'RESOLVED',
                'resolution': 'INCOMPLETE',
            }

    def filter_interesting_bugs(self, bugs):
        """Get the bugs with number of comments less than self.ncommments
        """

        def comment_handler(bug, bugid, data):
            if len(bug['comments']) <= self.ncomments:
                data.append(bugid)

        bugids = list(bugs.keys())
        data = []
        Bugzilla(
            bugids=bugids,
            commenthandler=comment_handler,
            commentdata=data,
            comment_include_fields=['count'],
        ).get_data().wait()

        bugs = {bugid: bugs[bugid] for bugid in data}

        return bugs

    def get_bz_params(self, date):
        fields = ['creator', 'flags']
        params = {
            'include_fields': fields,
            'resolution': '---',
            'f1': 'flagtypes.name',
            'o1': 'substring',
            'v1': 'needinfo?',
            'f2': 'days_elapsed',
            'o2': 'greaterthan',
            'v2': self.ndays,
        }

        return params

    def handle_bug(self, bug, data):
        creator = bug['creator']
        if self.people.is_mozilla(creator):
            return None

        for flag in utils.get_needinfo(bug):
            if flag.get('requestee', '') == creator:
                bugid = str(bug['id'])
                nick = bug['creator_detail']['nick']
                data[bugid] = {'creator_nick': nick}
                return bug
        return None

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(NewbieWithNI, self).get_bugs(date=date, bug_ids=bug_ids)
        bugs = self.filter_interesting_bugs(bugs)
        self.set_autofix(bugs)

        return bugs


if __name__ == '__main__':
    NewbieWithNI().run()
