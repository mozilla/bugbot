# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
from auto_nag.bugbug_utils import BugbugScript
from bugbug.models.component import ComponentModel


class Component(BugbugScript):
    def __init__(self):
        super(Component, self).__init__()
        self.model = ComponentModel.load(self.retrieve_model('component'))
        self.autofix_component = {}

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
        return 'Assign a component to untriaged bugs'

    def name(self):
        return 'component'

    def template(self):
        return 'component.html'

    def subject(self):
        return f'[Using ML] Assign a component to untriaged bugs ({self.frequency})'  # noqa

    def columns(self):
        return ['id', 'summary', 'component', 'confidence', 'autofixed']

    def sort_columns(self):
        return lambda p: (-p[3], -int(p[0]))

    def get_bz_params(self, date):
        params = {
            'component': 'Untriaged',
            # Ignore bugs for which somebody has ever modified the product or the component.
            'n1': 1, 'f1': 'product', 'o1': 'changedafter', 'v1': '1970-01-01',
            'n2': 1, 'f2': 'component', 'o2': 'changedafter', 'v2': '1970-01-01',
            'limit': 100, 'order': 'bug_id desc',
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        # Retrieve bugs to analyze.
        all_bug_data = super(Component, self).get_bugs(date=date, bug_ids=bug_ids)

        bugs = all_bug_data['bugs']

        # Retrieve history.
        self.retrieve_history(bugs)

        # Retrieve comments and attachments.
        self.retrieve_comments_and_attachments(bugs)

        bugs = list(bugs.values())

        # Analyze bugs (make a copy as bugbug could change some properties of the objects).
        probs = self.model.classify(copy.deepcopy(bugs), True)

        # Get the encoded component.
        indexes = probs.argmax(axis=-1)
        # Apply inverse transformation to get the component name from the encoded value.
        components = self.model.clf._le.inverse_transform(indexes)

        results = {}
        for bug, prob, index, component in zip(bugs, probs, indexes, components):
            # Skip product-only suggestions that are not useful.
            if '::' not in component and bug['product'] == component:
                continue

            component = self.model.CONFLATED_COMPONENTS_MAPPING.get(component, component)

            bug_id = str(bug['id'])

            result = {
                'id': bug_id,
                'summary': self.get_summary(bug),
                'component': component,
                'confidence': int(round(100 * prob[index])),
                'autofixed': False,
            }

            # In daily mode, we send an email with all results.
            if self.frequency == 'daily':
                results[bug_id] = result

            if prob[index] >= self.get_config('confidence_threshold'):
                # If we were able to predict both product and component, assign both product and component.
                # Otherwise, just change the product.
                if '::' in component:
                    i = component.index('::')
                    self.autofix_component[bug_id] = {
                        'product': component[:i],
                        'component': component[i + 2:],
                    }
                else:
                    self.autofix_component[bug_id] = {'product': component}

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


if __name__ == '__main__':
    Component().run()
