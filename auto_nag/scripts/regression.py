# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
import re
from auto_nag.bzcleaner import BzCleaner


COMMENTS_PAT = re.compile('^>.*[\n]?', re.MULTILINE)
HAS_UPLIFT_PAT = re.compile(
    r'(Feature/Bug causing the regression)|(feature/regressing bug #)', re.I
)
UPLIFT1_PAT = re.compile(
    r'[\[]?Feature/Bug causing the regression[\]]?:\n*(?:(?:[ \t]*)|(?:[^0-9]*bug[ \t]*))([0-9]+)[^\n]*$',
    re.MULTILINE | re.I,
)
UPLIFT2_PAT = re.compile(
    r'[\[]?Bug caused by[\]]? \(feature/regressing bug #\):\n*(?:(?:[ \t]*)|(?:[^0-9]*bug[ \t]*))([0-9]+)[^\n]*$',
    re.MULTILINE | re.I,
)
REG_BY_BUG_PAT = re.compile(
    r'[ \t]regress[^0-9\.,;\n]+(?:bug[ \t]*)([0-9]+)(?:[^\.\n\?]*[\.\n])?', re.I
)
CAUSED_BY_PAT = re.compile('caused by bug[ \t]*([0-9]+)', re.I)
REG_PAT = re.compile(
    r'(regression is)|(regression range)|(regressed build)|(mozregression)|(this is a regression)|(this regression)|(is a recent regression)|(regression version is)|(regression[- ]+window)',
    re.I,
)


class Regression(BzCleaner):
    def __init__(self):
        super(Regression, self).__init__()

    def description(self):
        return 'Get bugs with missing regression keyword'

    def name(self):
        return 'regression'

    def template(self):
        return 'regression.html'

    def subject(self):
        return 'Bugs with missing regression keyword'

    def ignore_bug_summary(self):
        return False

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        resolution_blacklist = self.get_config('resolution_blacklist', default=[])
        resolution_blacklist = ' '.join(resolution_blacklist)
        fields = ['keywords', 'cf_has_regression_range']
        params = {
            'include_fields': fields,
            'f1': 'keywords',
            'o1': 'notsubstring',
            'v1': 'regression',
            'f2': 'longdesc',
            'o2': 'anywordssubstr',
            'v2': 'regress caus',
            'f3': 'resolution',
            'o3': 'nowords',
            'v3': resolution_blacklist,
            'f4': 'longdesc',
            'o4': 'changedafter',
            'v4': start_date,
            'f5': 'longdesc',
            'o5': 'changedbefore',
            'v5': end_date,
        }

        return params

    def get_data(self):
        return {'regressions': set(), 'others': [], 'summaries': {}}

    def bughandler(self, bug, data):
        keywords = bug.get('keywords', [])
        if 'regressionwindow-wanted' in keywords:
            data['regressions'].add(bug['id'])
        else:
            has_regression_range = bug.get('cf_has_regression_range', '---')
            if has_regression_range == 'yes':
                data['regressions'].add(bug['id'])
            else:
                data['others'].append(bug['id'])
        data['summaries'][bug['id']] = self.get_summary(bug)

    def clean_comment(self, comment):
        return COMMENTS_PAT.sub('', comment)

    def has_uplift(self, comment):
        m = HAS_UPLIFT_PAT.search(comment)
        return bool(m)

    def find_bug_reg(self, comment):
        if self.has_uplift(comment):
            pats = [UPLIFT1_PAT, UPLIFT2_PAT]
            for pat in pats:
                m = pat.search(comment)
                if m:
                    return m.group(1)
            return ''
        else:
            pats = [REG_BY_BUG_PAT, CAUSED_BY_PAT]
            for pat in pats:
                m = pat.search(comment)
                if m:
                    return m.group(1)
            return None

    def has_reg_str(self, comment):
        m = REG_PAT.search(comment)
        return bool(m)

    def analyze_comments(self, bugids):
        """Analyze the comments to find regression"""

        def comment_handler(bug, bugid, data):
            bugid = int(bugid)
            for comment in bug['comments']:
                comment = self.clean_comment(comment['text'])
                reg_bug = self.find_bug_reg(comment)
                if reg_bug is None:
                    if self.has_reg_str(comment):
                        data[bugid] = True
                        break
                elif reg_bug:
                    data[bugid] = True
                    break

        data = {bugid: False for bugid in bugids}
        Bugzilla(
            bugids=bugids,
            commenthandler=comment_handler,
            commentdata=data,
            comment_include_fields=['text'],
        ).get_data().wait()

        return data

    def analyze_history(self, bugids):
        def history_handler(history, data):
            bugid = int(history['id'])
            for h in history['history']:
                changes = h.get('changes', [])
                for change in changes:
                    if (
                        change['field_name'] == 'keywords'
                        and change['removed'] == 'regression'
                    ):
                        data.add(bugid)
                        return

        data = set()
        Bugzilla(
            bugids=bugids, historyhandler=history_handler, historydata=data
        ).get_data().wait()

        return bugids - data

    def get_bugs(self, date='today', bug_ids=[]):
        bugids = super(Regression, self).get_bugs(date=date, bug_ids=bug_ids)
        data = self.analyze_comments(bugids['others'])
        reg_bugids = {bugid for bugid, reg in data.items() if reg}
        reg_bugids = self.analyze_history(reg_bugids)
        reg_bugids |= bugids['regressions']
        reg_bugids = [(n, bugids['summaries'][n]) for n in reg_bugids]

        return sorted(reg_bugids, reverse=True)


if __name__ == '__main__':
    Regression().run()
