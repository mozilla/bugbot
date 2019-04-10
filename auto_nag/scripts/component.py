# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import logger
from auto_nag.bugbug_utils import BugbugScript
from bugbug.models.component import ComponentModel


class Component(BugbugScript):
    def __init__(self):
        super().__init__()
        self.model = ComponentModel.load(self.retrieve_model())
        self.autofix_component = {}
        self.frequency = 'daily'

    def add_custom_arguments(self, parser):
        parser.add_argument(
            '--frequency',
            help='Daily (noisy) or Hourly',
            choices=['daily', 'hourly'],
            default='daily',
        )

    def parse_custom_arguments(self, args):
        self.frequency = args.frequency

    def description(self):
        return (
            f'[Using ML] Assign a component to untriaged bugs ({self.frequency})'  # noqa
        )

    def columns(self):
        return ['id', 'summary', 'component', 'confidence', 'autofixed']

    def sort_columns(self):
        return lambda p: (-p[3], -int(p[0]))

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)

        return {
            # Ignore bugs for which somebody has ever modified the product or the component.
            'n1': 1,
            'f1': 'product',
            'o1': 'changedafter',
            'v1': '1970-01-01',
            'n2': 1,
            'f2': 'component',
            'o2': 'changedafter',
            'v2': '1970-01-01',
            # Ignore closed bugs.
            'bug_status': '__open__',
            # Get recent General bugs, and all Untriaged bugs.
            'j3': 'OR',
            'f3': 'OP',
            'j4': 'AND',  # noqa
            'f4': 'OP',  # noqa
            'f5': 'component',
            'o5': 'equals',
            'v5': 'General',  # noqa
            'f6': 'creation_ts',
            'o6': 'greaterthan',
            'v6': start_date,  # noqa
            'f7': 'CP',  # noqa
            'f8': 'component',
            'o8': 'equals',
            'v8': 'Untriaged',  # noqa
            'f9': 'CP',
        }

    def get_bugs(self, date='today', bug_ids=[]):
        # Retrieve bugs to analyze.
        bugs, probs = super().get_bugs(date=date, bug_ids=bug_ids)
        if len(bugs) == 0:
            return {}

        # Get the encoded component.
        indexes = probs.argmax(axis=-1)
        # Apply inverse transformation to get the component name from the encoded value.
        suggestions = self.model.clf._le.inverse_transform(indexes)

        results = {}
        for bug, prob, index, suggestion in zip(bugs, probs, indexes, suggestions):
            # Skip product-only suggestions that are not useful.
            if '::' not in suggestion and bug['product'] == suggestion:
                continue

            suggestion = self.model.CONFLATED_COMPONENTS_MAPPING.get(
                suggestion, suggestion
            )

            if '::' not in suggestion:
                logger.error(
                    f'There is something wrong with this component suggestion! {suggestion}'
                )  # noqa
                continue

            i = suggestion.index('::')
            suggested_product = suggestion[:i]
            suggested_component = suggestion[i + 2 :]  # NOQA

            # When moving bugs out of the 'General' component, we don't want to change the product (unless it is Firefox).
            if bug['component'] == 'General' and bug['product'] not in {
                suggested_product,
                'Firefox',
            }:
                continue

            bug_id = str(bug['id'])

            result = {
                'id': bug_id,
                'summary': self.get_summary(bug),
                'component': suggestion,
                'confidence': int(round(100 * prob[index])),
                'autofixed': False,
            }

            # In daily mode, we send an email with all results.
            if self.frequency == 'daily':
                results[bug_id] = result

            confidence_threshold_conf = (
                'confidence_threshold'
                if bug['component'] != 'General'
                else 'general_confidence_threshold'
            )

            if prob[index] >= self.get_config(confidence_threshold_conf):
                self.autofix_component[bug_id] = {
                    'product': suggested_product,
                    'component': suggested_component,
                }

                result['autofixed'] = True

                # In hourly mode, we send an email with only the bugs we acted upon.
                if self.frequency == 'hourly':
                    results[bug_id] = result

        return results

    def get_autofix_change(self):
        cc = {'cc': {'add': self.get_config('cc')}}
        return {
            bug_id: (data.update(cc) or data)
            for bug_id, data in self.autofix_component.items()
        }

    def get_db_extra(self):
        return {
            bugid: '{}::{}'.format(v['product'], v['component'])
            for bugid, v in self.get_autofix_change().items()
        }


if __name__ == '__main__':
    Component().run()
