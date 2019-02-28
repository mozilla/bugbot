# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from auto_nag.bugbug_utils import BugbugScript
from bugbug.models.component import ComponentModel


class Component(BugbugScript):
    def __init__(self):
        super(Component, self).__init__()
        self.model = ComponentModel.load(self.retrieve_model('component'))
        self.autofix_component = {}

    def add_custom_arguments(self, parser):
        parser.add_argument('--frequency', help='Daily (noisy) or Hourly', choices=['daily', 'hourly'], default='daily')

    def parse_custom_arguments(self, args):
        self.frequency = args.frequency
        print(self.frequency)

    def description(self):
        return 'Assign a component to untriaged bugs'

    def name(self):
        return 'component'

    def template(self):
        return 'component.html'

    def subject(self):
        return f'[Using ML] Assign a component to untriaged bugs ({self.frequency})'

    def columns(self):
        return ['id', 'summary', 'component', 'confidence']

    def sort_columns(self):
        return lambda p: (-p[3], -int(p[0]))

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        params = {
            'component': 'Untriaged',
            'chfield': '[Bug creation]',
            'chfieldfrom': start_date,
            'chfieldto': end_date,
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        # Retrieve bugs to analyze.
        all_bug_data = super(Component, self).get_bugs(date=date, bug_ids=bug_ids)

        bugs = all_bug_data['bugs']

        # Retrieve history.
        self.retrieve_history(bugs)

        # Retrieve comments.
        self.retrieve_comments(bugs)

        # Retrieve attachments.
        self.retrieve_attachments(bugs)

        bugs = list(bugs.values())

        # Analyze bugs.
        probs = self.model.classify(bugs, True)

        # Get the encoded component.
        indexes = probs.argmax(axis=-1)
        # Apply inverse transformation to get the component name from the encoded value.
        components = self.model.clf._le.inverse_transform(indexes)

        results = {}
        for bug, prob, index, component in zip(bugs, probs, indexes, components):
            # Skip product-only suggestions that are not useful.
            if '::' not in component and (bug['product'] == component or component in ['Core', 'Firefox', 'Toolkit']):
                continue

            bug_id = str(bug['id'])

            result = {
                'id': bug_id,
                'summary': self.get_summary(bug),
                'component': component,
                'confidence': int(round(100 * prob[index])),
            }

            # In daily mode, we send an email with all results.
            if self.frequency == 'daily':
                results[bug_id] = result

            if prob[index] >= self.get_config('confidence_threshold'):
                # If we were able to predict both product and component, assign both product and component.
                # Otherwise, just change the product.
                if '::' in component:
                    self.autofix_component[bug_id] = {
                        'product': component[:component.index('::')],
                        'component': component[component.index('::') + 2:],
                    }
                else:
                    self.autofix_component[bug_id] = {
                        'product': component,
                    }

                # In hourly mode, we send an email with only the bugs we acted upon.
                if self.frequency == 'hourly':
                    results[bug_id] = result

        return results

    def has_individual_autofix(self):
        return True

    def get_autofix_change(self):
        cc = {'cc': {'add': self.get_config('cc')}}
        return {bug_id: (data.update(cc) or data) for bug_id, data in self.autofix_component.items()}


if __name__ == '__main__':
    Component().run()
