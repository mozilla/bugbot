# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
from dateutil.relativedelta import relativedelta
from libmozdata.bugzilla import Bugzilla
from libmozdata.connection import Query
from libmozdata.release_calendar import get_calendar
from libmozdata import utils as lmdutils, hgmozilla
import re
import whatthepatch
from auto_nag.bzcleaner import BzCleaner
from auto_nag.common import get_current_versions
from auto_nag.people import People
from auto_nag import utils


NIGHTLY_PAT = Bugzilla.get_landing_patterns(channels=['nightly'])
BUG_PAT = re.compile('[\t ]*bug[\t ]*([0-9]+)', re.I)
BACKOUT_PAT = re.compile('^back(ed)?[ \t]*out', re.I)


class CodeFreezeWeek(BzCleaner):
    def __init__(self):
        super(CodeFreezeWeek, self).__init__()
        versions = get_current_versions()
        self.people = People()
        self.nightly = versions['central']
        self.beta = versions['beta']
        self.release = versions['release']
        self.status_nightly = utils.get_flag(self.nightly, 'status', 'central')
        self.status_beta = utils.get_flag(self.beta, 'status', 'beta')
        self.status_release = utils.get_flag(self.release, 'status', 'release')
        self.tracking_nightly = utils.get_flag(self.nightly, 'tracking', 'central')
        self.tracking_beta = utils.get_flag(self.beta, 'tracking', 'beta')
        self.tracking_release = utils.get_flag(self.release, 'tracking', 'release')

    def description(self):
        return 'Bugs with patches which landed during the soft freeze week'

    def name(self):
        return 'code-freeze-week'

    def template(self):
        return 'code_freeze_week.html'

    def subject(self):
        return self.description()

    def get_extra_for_template(self):
        return {
            'nightly': self.nightly,
            'beta': self.beta,
            'release': self.release,
            'date': lmdutils.get_date_str(self.date),
        }

    def filter_no_nag_keyword(self):
        return False

    def must_run(self, date):
        for c in get_calendar():
            # if freeze is the 2019-03-11, then the tool must run the day after
            # until 2019-03-2018 (a week after)
            freeze = c['soft freeze']
            if freeze <= date <= freeze + relativedelta(days=6):
                return True
        return False

    def has_product_component(self):
        return True

    def columns(self):
        return [
            'id',
            'summary',
            'product',
            'component',
            'assignee',
            'landed_patches',
            'addlines',
            'rmlines',
            'size',
            'test_size',
            'priority',
            'severity',
            'tracking',
            'status',
            'crash',
            'keywords',
        ]

    def sort_columns(self):
        return lambda p: (p[2], p[3], -p[5], -p[8], -p[9], -int(p[0]))

    def handle_bug(self, bug, data):
        bugid = str(bug['id'])

        assignee = bug.get('assigned_to', '')
        if assignee:
            info = self.people.get_info(assignee)
            if info:
                assignee = info['cn']
            else:
                name = bug.get('assigned_to_detail', {}).get('real_name', '')
                if name:
                    assignee = utils.get_better_name(name)
        else:
            assignee = 'Nobody'

        isacrash = len(utils.get_signatures(bug.get('cf_crash_signature', ''))) != 0

        data[bugid] = {
            'land': {},
            'assignee': assignee,
            'crash': 'Yes' if isacrash else 'No',
            'priority': bug['priority'],
            'severity': bug['severity'],
            'tracking': bug[self.tracking_nightly],
            'status': {
                self.nightly: bug[self.status_nightly],
                self.beta: bug[self.status_beta],
                self.release: bug[self.status_release],
            },
            'keywords': ','.join(bug['keywords']),
        }

        return bug

    def filter_bugs(self, bugs):
        invalids = set()

        def comment_handler(bug, bugid, data):
            r = Bugzilla.get_landing_comments(bug['comments'], [], NIGHTLY_PAT)
            if not r:
                invalids.add(bugid)
                return

            data[bugid]['land'] = {
                i['revision']: {'date': None, 'backedout': False, 'bugid': bugid}
                for i in r
            }

        def history_handler(history, data):
            bugid = str(history['id'])
            history = history['history']
            valid = False
            for changes in history:
                for change in changes['changes']:
                    if (
                        change['field_name'] == 'resolution'
                        and change['added'] == 'FIXED'
                    ):
                        when = lmdutils.get_date_ymd(changes['when'])
                        valid = self.date <= when < self.tomorrow

            if not valid:
                invalids.add(bugid)

        bugids = list(bugs.keys())
        Bugzilla(
            bugids=bugids,
            commenthandler=comment_handler,
            commentdata=bugs,
            historyhandler=history_handler,
            historydata=bugs,
            comment_include_fields=['text'],
        ).get_data().wait()

        for bugid in invalids:
            if 'leave-open' not in bugs[bugid]['keywords']:
                del bugs[bugid]

    def patch_analysis(self, patch):
        info = {'size': 0, 'test_size': 0, 'addlines': 0, 'rmlines': 0}

        for diff in whatthepatch.parse_patch(patch):
            if diff.header and diff.changes:
                h = diff.header
                new_path = h.new_path[2:] if h.new_path.startswith('b/') else h.new_path

                # Calc changes additions & deletions
                counts = [
                    (old is None and new is not None, new is None and old is not None)
                    for old, new, _ in diff.changes
                ]
                counts = list(zip(*counts))  # inverse zip
                info['addlines'] += sum(counts[0])
                info['rmlines'] += sum(counts[1])

                if utils.is_test_file(new_path):
                    info['test_size'] += len(diff.changes)
                else:
                    info['size'] += len(diff.changes)

        return info

    def get_hg_patches(self, bugs):
        url = hgmozilla.RawRevision.get_url('nightly')
        queries = []

        def handler(patch, data):
            info = self.patch_analysis(patch)
            if 'addlines' not in data:
                data.update(info)
            else:
                for k, v in info.items():
                    data[k] += v

        for info in bugs.values():
            for rev, i in info['land'].items():
                if not i['backedout']:
                    queries.append(Query(url, {'node': rev}, handler, info))

        if queries:
            hgmozilla.Revision(queries=queries).wait()

        for info in bugs.values():
            info['landed_patches'] = [
                v['backedout'] for v in info['land'].values()
            ].count(False)

    def get_hg(self, bugs):
        url = hgmozilla.Revision.get_url('nightly')
        queries = []

        def handler_rev(json, data):
            push = json['pushdate'][0]
            push = datetime.datetime.utcfromtimestamp(push)
            push = lmdutils.as_utc(push)
            data['date'] = lmdutils.get_date_str(push)
            data['backedout'] = utils.is_backout(json)
            m = BUG_PAT.search(json['desc'])
            if not m or m.group(1) != data['bugid']:
                data['bugid'] = ''

        for info in bugs.values():
            for rev, i in info['land'].items():
                queries.append(Query(url, {'node': rev}, handler_rev, i))

        if queries:
            hgmozilla.Revision(queries=queries).wait()

        # clean
        bug_torm = []
        for bug, info in bugs.items():
            torm = []
            for rev, i in info['land'].items():
                if not i['bugid'] or not (
                    self.date <= lmdutils.get_date_ymd(i['date']) < self.tomorrow
                ):
                    torm.append(rev)
            for x in torm:
                del info['land'][x]
            if not info['land']:
                bug_torm.append(bug)
        for x in bug_torm:
            del bugs[x]

        self.get_hg_patches(bugs)

    def get_bz_params(self, date):
        self.date = lmdutils.get_date_ymd(date)
        self.tomorrow = self.date + relativedelta(days=1)
        fields = [
            'assigned_to',
            'assigned_to_detail',
            'status',
            'resolution',
            'priority',
            'severity',
            'keywords',
            'cf_crash_signature',
        ]
        fields += [self.status_nightly, self.status_beta, self.status_release]
        fields += [self.tracking_nightly]
        params = {
            'include_fields': fields,
            'j1': 'OR',
            'f1': 'OP',
            'j2': 'AND',
            'f2': 'OP',
            'f3': 'resolution',
            'o3': 'changedafter',
            'v3': self.date,
            'f4': 'resolution',
            'o4': 'changedbefore',
            'v4': self.tomorrow,
            'f5': 'resolution',
            'o5': 'equals',
            'v5': 'FIXED',
            'f6': 'CP',
            'j7': 'AND',
            'f7': 'OP',
            'f8': 'keywords',
            'o8': 'anywordssubstr',
            'v8': 'leave-open',
            'f9': 'keywords',
            'o9': 'changedafter',
            'v9': self.date - relativedelta(years=1),
            'f10': 'CP',
            'f11': 'CP',
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(CodeFreezeWeek, self).get_bugs(date=date, bug_ids=bug_ids)
        self.filter_bugs(bugs)
        self.get_hg(bugs)

        return bugs


if __name__ == '__main__':
    CodeFreezeWeek().run()
