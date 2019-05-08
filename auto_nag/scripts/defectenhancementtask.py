# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bugbug_utils import BugbugScript
from bugbug.models.defect_enhancement_task import DefectEnhancementTaskModel


class DefectEnhancementTask(BugbugScript):
    def __init__(self):
        self.model_class = DefectEnhancementTaskModel
        super().__init__()
        self.autofix_type = {}

    def description(self):
        return '[Using ML] Check that the bug type is the same as predicted by bugbug'

    def columns(self):
        return ['id', 'summary', 'type', 'bugbug_type', 'confidence', 'autofixed']

    def sort_columns(self):
        def _sort_columns(p):
            if p[2] == 'defect':  # defect -> non-defect is what we plan to autofix, so we show it first in the email.
                prio = 0
            elif p[3] == 'defect':  # non-defect -> defect has more priority than the rest, as 'enhancement' and 'task' can be often confused.
                prio = 1
            else:
                prio = 2

            # Then, we sort by confidence and ID.
            return (prio, -p[4], -p[0])

        return _sort_columns

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        reporter_blacklist = self.get_config('reporter_blacklist', default=[])
        reporter_blacklist = ','.join(reporter_blacklist)

        return {
            # Ignore closed bugs.
            'bug_status': '__open__',

            # Check only recently opened bugs.
            'f1': 'creation_ts', 'o1': 'greaterthan', 'v1': start_date,

            'f2': 'reporter', 'o2': 'nowords', 'v2': reporter_blacklist,
        }

    # Remove bugs for which the type was already changed.
    def remove_using_history(self, bugs):
        def should_remove(bug):
            for h in bug['history']:
                for change in h['changes']:
                    if change["field_name"] == "type":
                        return True

            return False

        return [bug for bug in bugs if not should_remove(bug)]

    def get_bugs(self, date='today', bug_ids=[]):
        # Retrieve bugs to analyze.
        bugs, probs = super().get_bugs(date=date, bug_ids=bug_ids)
        if len(bugs) == 0:
            return {}

        # Get the encoded type.
        indexes = probs.argmax(axis=-1)
        # Apply inverse transformation to get the type name from the encoded value.
        suggestions = self.model.clf._le.inverse_transform(indexes)

        results = {}
        for bug, prob, index, suggestion in zip(bugs, probs, indexes, suggestions):
            assert suggestion in {'defect', 'enhancement', 'task'}, f'Suggestion {suggestion} is invalid'  # noqa

            if bug['type'] == suggestion:
                continue

            results[bug['id']] = {
                'id': bug['id'],
                'summary': self.get_summary(bug),
                'type': bug['type'],
                'bugbug_type': suggestion,
                'confidence': int(round(100 * prob[index])),
                'autofixed': False,
            }

            # Only autofix results for which we are sure enough.
            # And only autofix defect -> task/enhancement for now, unless we're 100% sure.
            # if prob[index] >= self.get_config('confidence_threshold') and (bug['type'] == 'defect' or prob[index] == 1.0):
            # XXX: For now, only autofix bugs for which we are 100% sure.
            if prob[index] == 1.0:
                results[bug['id']]['autofixed'] = True
                self.autofix_type[bug['id']] = suggestion

        return results

    def get_autofix_change(self):
        cc = self.get_config('cc')
        return {
            bug_id: {
                'type': suggestion,
                'cc': {
                    'add': cc
                },
                'comment': {
                    'body': '[Bugbug](https://github.com/mozilla/bugbug/) thinks this bug is a [{}](https://mozilla.github.io/bug-handling/bug-types), but please change it back in case of error.'.format(suggestion),
                },
            }
            for bug_id, suggestion in self.autofix_type.items()
        }


if __name__ == '__main__':
    DefectEnhancementTask().run()
