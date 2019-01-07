# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
from auto_nag.bzcleaner import BzCleaner
import lzma
import shutil
from bugbug.models.regression import RegressionModel
from urllib.request import urlretrieve
import requests


class Regression(BzCleaner):
    def __init__(self):
        super(Regression, self).__init__()
        MODEL_URL = 'https://index.taskcluster.net/v1/task/project.releng.services.project.testing.bugbug_train.latest/artifacts/public/regressionmodel.xz'
        r = requests.head(MODEL_URL, allow_redirects=True)
        new_etag = r.headers['ETag']

        try:
            with open('regressionmodel.etag', 'r') as f:
                old_etag = f.read()
        except IOError:
            old_etag = None

        if old_etag != new_etag:
            urlretrieve(MODEL_URL, 'regressionmodel.xz')

            with lzma.open('regressionmodel.xz', 'rb') as input_f:
                with open('regressionmodel', 'wb') as output_f:
                    shutil.copyfileobj(input_f, output_f)

            with open('regressionmodel.etag', 'w') as f:
                f.write(new_etag)

        self.model = RegressionModel.load('regressionmodel')

    def description(self):
        return 'Get bugs with missing regression keyword'

    def name(self):
        return 'regression'

    def template(self):
        return 'regression.html'

    def subject(self):
        return '[Using ML] Bugs with missing regression keyword'

    def ignore_bug_summary(self):
        return False

    def all_include_fields(self):
        return True

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        resolution_blacklist = self.get_config('resolution_blacklist', default=[])
        resolution_blacklist = ' '.join(resolution_blacklist)
        params = {
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
        return {'regressions': set(), 'others': {}, 'summaries': {}}

    def bughandler(self, bug, data):
        keywords = bug.get('keywords', [])
        if 'regressionwindow-wanted' in keywords:
            data['regressions'].add(bug['id'])
        else:
            has_regression_range = bug.get('cf_has_regression_range', '---')
            if has_regression_range == 'yes':
                data['regressions'].add(bug['id'])
            else:
                data['others'][bug['id']] = bug
        data['summaries'][bug['id']] = self.get_summary(bug)

    def retrieve_comments(self, bugs):
        """Retrieve bug comments"""

        def comment_handler(bug, bug_id):
            bugs[int(bug_id)]['comments'] = bug['comments']

        Bugzilla(
            bugids=[bug_id for bug_id in bugs.keys()],
            commenthandler=comment_handler,
            comment_include_fields=['text'],
        ).get_data().wait()

    def retrieve_history(self, bugs):
        """Retrieve bug history"""

        def history_handler(bug):
            bugs[int(bug['id'])]['history'] = bug['history']

        Bugzilla(
            bugids=[bug_id for bug_id in bugs.keys()],
            historyhandler=history_handler,
        ).get_data().wait()

    def remove_using_history(self, bugs):
        to_remove = set()
        for bug_id, bug in bugs.items():
            for h in bug['history']:
                changes = h.get('changes', [])
                for change in changes:
                    if (
                        change['field_name'] == 'keywords'
                        and change['removed'] == 'regression'
                    ):
                        to_remove.add(bug_id)
                        return

        for bug_id in to_remove:
            del bugs[bug_id]

    def retrieve_attachments(self, bugs):
        """Retrieve bug attachments"""

        def attachment_handler(bug, bug_id):
            bugs[int(bug_id)]['attachments'] = bug

        Bugzilla(
            bugids=[bug_id for bug_id in bugs.keys()],
            attachmenthandler=attachment_handler,
            attachment_include_fields=['id', 'is_obsolete', 'flags', 'is_patch', 'creator', 'content_type'],
        ).get_data().wait()

    def get_bugs(self, date='today', bug_ids=[]):
        # Retrieve bugs to analyze.
        all_bug_data = super(Regression, self).get_bugs(date=date, bug_ids=bug_ids)

        bugs = all_bug_data['others']

        # Retrieve history.
        self.retrieve_history(bugs)

        # Remove bugs for which the regression keyword was set and removed in the past.
        self.remove_using_history(bugs)

        # Retrieve comments.
        self.retrieve_comments(bugs)

        # Retrieve attachments.
        self.retrieve_attachments(bugs)

        bugs = list(bugs.values())

        # Analyze bugs.
        probs = self.model.classify(bugs, True)

        reg_bugids = {bug['id'] for bug, prob in zip(bugs, probs) if prob[1] > 0.9}
        print(len(reg_bugids))

        # Add bugs that are certainly regressions.
        reg_bugids |= all_bug_data['regressions']

        # Attach summaries to bugs.
        reg_bugids = [(n, all_bug_data['summaries'][n]) for n in reg_bugids]

        return sorted(reg_bugids, reverse=True)


if __name__ == '__main__':
    Regression().run()
