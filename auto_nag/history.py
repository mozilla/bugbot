# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
from pprint import pprint

from auto_nag import logger, utils


class History(object):

    BOT = 'release-mgmt-account-bot@mozilla.tld'

    def __init__(self):
        super(History, self).__init__()
        Bugzilla.TOKEN = utils.get_login_info()['bz_api_key']

    def get_bugs(self):
        logger.info('History: get bugs: start...')

        def bug_handler(bug, data):
            data.add(bug['id'])

        fields = {
            'changedby': [
                'keywords',
                'product',
                'component',
                'assigned_to',
                'cf_crash_signature',
                'everconfirmed',
                'cf_has_regression_range',
                'cf_has_str',
                'priority',
                'bug_severity',
                'resolution',
                'bug_status',
                'bug_type',
                'cf_status_firefox68',
                'cf_status_firefox67',
                'cf_status_firefox66',
                'cf_status_firefox65',
                'cf_status_firefox64',
                'cf_status_firefox63',
                'cf_status_firefox62',
            ],
            'equals': ['commenter', 'setters.login_name'],
        }

        queries = []
        bugids = set()
        for op, fs in fields.items():
            for f in fs:
                params = {'include_fields': 'id', 'f1': f, 'o1': op, 'v1': History.BOT}
                queries.append(
                    Bugzilla(params, bughandler=bug_handler, bugdata=bugids, timeout=20)
                )

        for q in queries:
            q.get_data().wait()

        logger.info('History: get bugs: end.')

        return bugids

    def get_bug_info(self, bugids):
        logger.info('History: get bugs info: start...')

        def history_handler(bug, data):
            bugid = str(bug['id'])
            for h in bug['history']:
                if h['who'] == History.BOT:
                    del h['who']
                    data[bugid].append(h)

        def comment_handler(bug, bugid, data):
            bugid = str(bugid)
            for comment in bug['comments']:
                if comment['author'] == History.BOT:
                    text = comment['text']
                    data[bugid].append(
                        {'comment': text, 'date': comment['creation_time']}
                    )

        data = {str(bugid): [] for bugid in bugids}

        Bugzilla(
            list(data.keys()),
            historyhandler=history_handler,
            historydata=data,
            commenthandler=comment_handler,
            commentdata=data,
            timeout=960,
        ).get_data().wait()

        logger.info('History: get bugs info: end.')

        return data

    def cleanup(self, data):
        # res is a dictionary: change_date_time => change or comment
        res = {}

        for bugid, info in data.items():
            res[bugid] = x = {}
            for c in info:
                if 'changes' in c:
                    when = c['when']
                    del c['when']
                    if when not in x:
                        x[when] = {'changes': c['changes']}
                    else:
                        x[when]['changes'] += c['changes']
                if 'comment' in c:
                    when = c['date']
                    del c['date']
                    if when not in x:
                        x[when] = {'comment': c['comment']}
                    else:
                        x[when]['comment'] = c['comment']
        return res

    def get_pc(self, changes):
        p = ''
        c = ''
        for change in changes:
            if change.get('field_name') == 'component' and 'added' in change:
                c = change['added']
            if change.get('field_name') == 'product' and 'added' in change:
                p = change['added']
        return '{}::{}'.format(p, c)

    def get_ni(self, changes):
        for change in changes:
            if change.get('field_name') == 'flagtypes.name' and 'added' in change:
                c = change['added']
                ni = 'needinfo?('
                if c.startswith(ni):
                    return c[len(ni) : -1]  # NOQA
        return ''

    def guess_tool(self, data):
        res = []
        no_tool = []

        for bugid, info in data.items():
            for date, i in info.items():
                if 'comment' in i:
                    c = i['comment']
                    if c.startswith('Crash volume for signature'):
                        continue

                    tool = None
                    if c.startswith(
                        'The leave-open keyword is there and there is no activity for'
                    ):
                        tool = 'leave_open_no_activity'
                    elif c.startswith('Closing because no crashes reported for'):
                        tool = 'no_crashes'
                    elif c.startswith('Moving to p3 because no activity for at least'):
                        tool = 'old_p2_bug'
                    elif c.startswith('Moving to p2 because no activity for at least'):
                        tool = 'old_p1_bug'
                    elif c.startswith(
                        'There\'s a r+ patch which didn\'t land and no activity in this bug'
                    ) or c.startswith(
                        'There are some r+ patches which didn\'t land and no activity in this bug for'
                    ):
                        tool = 'not_landed'
                    elif c.startswith(
                        'The meta keyword is there, the bug doesn\'t depend on other bugs and there is no activity for'
                    ):
                        tool = 'meta_no_deps_no_activity'
                    elif (
                        '[mozregression](https://wiki.mozilla.org/Auto-tools/Projects/Mozregression)'
                        in c
                    ):
                        tool = 'has_str_no_range'
                    elif (
                        'as the bug is tracked by a release manager for the current nightly'
                        in c
                    ):
                        tool = 'mismatch_priority_tracking_nightly'
                    elif (
                        'as the bug is tracked by a release manager for the current beta'
                        in c
                    ):
                        tool = 'mismatch_priority_tracking_beta'
                    elif (
                        'as the bug is tracked by a release manager for the current release'
                        in c
                    ):
                        tool = 'mismatch_priority_tracking_release'
                    elif c.startswith('The priority flag is not set for this bug.\n:'):
                        tool = 'no_priority'
                    elif c.startswith(
                        'The priority flag is not set for this bug and there is no activity for'
                    ):
                        tool = 'ni_triage_owner'

                    if tool is None:
                        no_tool.append((bugid, info))
                    else:
                        extra = self.get_ni(i.get('changes', []))
                        res.append(
                            {'tool': tool, 'date': date, 'bugid': bugid, 'extra': extra}
                        )
                else:
                    changes = i['changes']
                    N = len(res)
                    for change in changes:
                        if change.get('added') == 'meta':
                            res.append(
                                {
                                    'tool': 'summary_meta_missing',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif change.get('field_name') in {'component', 'product'}:
                            res.append(
                                {
                                    'tool': 'component',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': self.get_pc(changes),
                                }
                            )
                            break
                        elif change.get('field_name') == 'cf_has_str':
                            res.append(
                                {
                                    'tool': 'has_str_no_hasstr',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif change.get('removed') == 'leave-open':
                            res.append(
                                {
                                    'tool': 'leave_open',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif change.get('field_name') == 'assigned_to':
                            res.append(
                                {
                                    'tool': 'no_assignee',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': change['added'],
                                }
                            )
                            break
                        elif (
                            change.get('field_name', '').startswith('cf_status_firefox')
                            and change.get('added') == 'affected'
                        ):
                            res.append(
                                {
                                    'tool': 'nighty_reopened',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif (
                            change.get('field_name') == 'status'
                            and change.get('added') == 'ASSIGNED'
                        ):
                            res.append(
                                {
                                    'tool': 'assignee_but_unconfirmed',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif (
                            change.get('field_name') == 'keywords'
                            and change.get('added') == 'regression'
                        ):
                            res.append(
                                {
                                    'tool': 'regression',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif (
                            change.get('field_name') == 'severity'
                            and change.get('added') == 'major'
                        ):
                            res.append(
                                {
                                    'tool': 'tracked_bad_severity',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif change.get('field_name') == 'cf_crash_signature':
                            res.append(
                                {
                                    'tool': 'copy_duplicate_info',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif (
                            change.get('field_name') == 'keywords'
                            and change.get('removed') == 'stalled'
                        ):
                            res.append(
                                {
                                    'tool': 'regression',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif (
                            change.get('field_name') == 'type'
                            and change.get('added') == 'defect'
                        ):
                            res.append(
                                {
                                    'tool': 'regression_but_type_enhancement_task',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif (
                            change.get('field_name') == 'keywords'
                            and change.get('removed') == 'dupeme'
                        ):
                            res.append(
                                {
                                    'tool': 'closed_dupeme',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif (
                            change.get('field_name') == 'keywords'
                            and change.get('added') == 'dupeme'
                        ):
                            res.append(
                                {
                                    'tool': 'dupeme_whiteboard_keyword',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif change.get('field_name') == 'summary' and change.get(
                            'added'
                        ).startswith('[meta]'):
                            res.append(
                                {
                                    'tool': 'meta_summary_missing',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break
                        elif change.get('field_name', '').startswith(
                            'cf_status_firefox'
                        ) and change.get('added') in {
                            '?',
                            'fixed',
                            'verified',
                            'unaffected',
                        }:
                            res.append(
                                {
                                    'tool': 'missing_beta_status',
                                    'date': date,
                                    'bugid': bugid,
                                    'extra': '',
                                }
                            )
                            break

                    if len(res) == N:
                        no_tool.append((bugid, info))

        if no_tool:
            pprint(no_tool)

        return res

    def get(self):
        bugids = self.get_bugs()
        bugs = self.get_bug_info(bugids)
        bugs = self.cleanup(bugs)
        hist = self.guess_tool(bugs)

        return hist
