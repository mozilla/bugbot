# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bugbug_utils import BugbugScript
from bugbug.models.regression import RegressionModel


class Regression(BugbugScript):
    def __init__(self):
        super(Regression, self).__init__()
        self.model = RegressionModel.load(self.retrieve_model('regression'))
        self.autofix_regression = []

    def description(self):
        return 'Get bugs with missing regression keyword'

    def name(self):
        return 'regression'

    def template(self):
        return 'regression.html'

    def subject(self):
        return '[Using ML] Bugs with missing regression keyword'

    def columns(self):
        return ['id', 'summary', 'confidence']

    def sort_columns(self):
        return lambda p: (-p[2], -int(p[0]))

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)

        resolution_blacklist = self.get_config('resolution_blacklist', default=[])
        resolution_blacklist = ' '.join(resolution_blacklist)

        reporter_blacklist = self.get_config('reporter_blacklist', default=[])
        reporter_blacklist = ','.join(reporter_blacklist)

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
            'f6': 'reporter',
            'o6': 'nowords',
            'v6': reporter_blacklist,
        }

        return params

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

    def get_bugs(self, date='today', bug_ids=[]):
        # Retrieve bugs to analyze.
        all_bug_data = super(Regression, self).get_bugs(date=date, bug_ids=bug_ids)

        bugs = all_bug_data['bugs']

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

        result = {}
        for bug, prob in zip(bugs, probs):
            if prob[1] < 0.5:
                continue

            bug_id = str(bug['id'])
            result[bug_id] = {
                'id': bug_id,
                'summary': self.get_summary(bug),
                'confidence': int(round(100 * prob[1])),
            }

            # Only autofix results for which we are sure enough.
            if prob[1] >= self.get_config('confidence_threshold'):
                self.autofix_regression.append(bug_id)

        return result

    def has_individual_autofix(self):
        return True

    def get_autofix_change(self):
        cc = self.get_config('cc')
        return {bug_id: {'keywords': {'add': ['regression']},
                         'cc': {'add': cc} for bug_id in self.autofix_regression}


if __name__ == '__main__':
    Regression().run()
