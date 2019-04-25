# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import dateutil.parser
from libmozdata.bugzilla import Bugzilla, BugzillaUser
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class RegressionWithoutRegressedBy(BzCleaner):
    def __init__(self):
        super(RegressionWithoutRegressedBy, self).__init__()

    def description(self):
        return 'Regressions without regressed_by and some dependencies'

    def handle_bug(self, bug, data):
        bugid = bug['id']
        deps = set(bug['blocks']) | set(bug['depends_on'])
        assignee = bug['assigned_to_detail']
        if utils.is_no_assignee(assignee['email']):
            assignee = None

        data[str(bugid)] = {
            'deps': deps,
            'assignee': assignee,
            'creator': bug['creator_detail'],
            'creation': dateutil.parser.parse(bug['creation_time']),
        }
        return bug

    def filter_bugs(self, bugs):
        all_deps = set()
        dep_bug_creation = {}

        for bugid, info in bugs.items():
            bugid = int(bugid)
            info['deps'] = deps = set(x for x in info['deps'] if x < bugid)
            if deps:
                all_deps |= deps
                for dep in deps:
                    dep_bug_creation[dep] = info['creation']

        def bug_handler(bug, data):
            if 'meta' in bug['keywords'] or not bug['cf_last_resolved']:
                data.add(bug['id'])

        def history_handler(bug, data):
            bugid = bug['id']
            resolved_before = False
            for h in bug['history']:
                if resolved_before:
                    break
                for change in h['changes']:
                    if change.get(
                        'field_name', ''
                    ) == 'cf_last_resolved' and change.get('added', ''):
                        date = dateutil.parser.parse(change['added'])
                        if date < dep_bug_creation[bugid]:
                            resolved_before = True
                            break
            if not resolved_before:
                data.add(bugid)

        invalids = set()
        Bugzilla(
            bugids=list(all_deps),
            include_fields=['id', 'keywords', 'cf_last_resolved'],
            bughandler=bug_handler,
            bugdata=invalids,
            historyhandler=history_handler,
            historydata=invalids,
        ).get_data().wait()

        to_rm = []
        for bugid, info in bugs.items():
            deps = info['deps'] - invalids
            if not deps:
                to_rm.append(bugid)
            else:
                info['deps'] = deps

        for bugid in to_rm:
            del bugs[bugid]

        return bugs

    def set_autofix(self, bugs):
        def history_handler(bug, data):
            stats = {}
            for h in bug['history']:
                for change in h['changes']:
                    if change.get('field_name', '') in {
                        'blocks',
                        'depends_on',
                    } and change.get('added', ''):
                        who = h['who']
                        stats[who] = stats.get(who, 0) + 1

            bugid = str(bug['id'])
            data[bugid]['winner'] = (
                max(stats.items(), key=lambda p: p[1])[0] if stats else None
            )

        no_assignee = [bugid for bugid, info in bugs.items() if not info['assignee']]
        Bugzilla(
            bugids=no_assignee, historyhandler=history_handler, historydata=bugs
        ).get_data().wait()

        no_nick = {}
        for bugid, info in bugs.items():
            if info['assignee']:
                winner = {
                    'mail': info['assignee']['email'],
                    'nickname': info['assignee']['nick'],
                }
                self.add_auto_ni(bugid, winner)
            elif info['winner']:
                winner = info['winner']
                if winner not in no_nick:
                    no_nick[winner] = []
                no_nick[winner].append(bugid)
            else:
                winner = {
                    'mail': info['creator']['email'],
                    'nickname': info['creator']['nick'],
                }
                self.add_auto_ni(bugid, winner)

        if no_nick:

            def user_handler(user, data):
                data[user['name']] = user['nick']

            data = {}
            BugzillaUser(
                user_names=list(no_nick.keys()),
                include_fields=['name', 'nick'],
                user_handler=user_handler,
                user_data=data,
            ).wait()

            for bzmail, bugids in no_nick.items():
                nick = data[bzmail]
                for bugid in bugids:
                    self.add_auto_ni(bugid, {'mail': bzmail, 'nickname': nick})

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        fields = ['blocks', 'depends_on', 'assigned_to', 'creator', 'creation_time']
        reporter_blacklist = self.get_config('reporter_blacklist', default=[])
        reporter_blacklist = ','.join(reporter_blacklist)
        params = {
            'include_fields': fields,
            'bug_status': '__open__',
            'j1': 'OR',
            'f1': 'OP',
            'f2': 'keywords',
            'o2': 'casesubstring',
            'v2': 'regression',
            'f3': 'cf_has_regression_range',
            'o3': 'equals',
            'v3': 'yes',
            'f4': 'CP',
            'f5': 'regressed_by',
            'o5': 'isempty',
            'n6': 1,
            'f6': 'regressed_by',
            'o6': 'changedafter',
            'v6': '1970-01-01',
            'j7': 'OR',
            'f7': 'OP',
            'f8': 'blocked',
            'o8': 'isnotempty',
            'f9': 'dependson',
            'o9': 'isnotempty',
            'f10': 'CP',
            'f11': 'creation_ts',
            'o11': 'greaterthan',
            'v11': start_date,
            'f12': 'keywords',
            'o12': 'nowords',
            'v12': 'regressionwindow-wanted',
            'f13': 'reporter',
            'o13': 'nowords',
            'v13': reporter_blacklist,
            'n14': 1,
            'f14': 'longdesc',
            'o14': 'casesubstring',
            'v14': 'since this bug is a regression, could you fill (if possible) the regressed_by field',
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(RegressionWithoutRegressedBy, self).get_bugs(
            date=date, bug_ids=bug_ids
        )
        bugs = self.filter_bugs(bugs)
        self.set_autofix(bugs)

        return bugs


if __name__ == '__main__':
    RegressionWithoutRegressedBy().run()
