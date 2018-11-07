# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class MetaSummaryMissing(BzCleaner):

    def __init__(self):
        super(MetaSummaryMissing, self).__init__()
        self.products = utils.get_config('common', 'products')

    def description(self):
        return 'Get bugs with the meta keyword but not [meta] in the title'

    def name(self):
        return 'meta_summary_missing'

    def template(self):
        return 'meta_summary_missing.html'

    def subject(self):
        return self.description()

    def ignore_bug_summary(self):
        return False

    def get_bz_params(self, date):
        days_lookup = self.get_config('days_lookup', default=180)
        return {
            'resolution': ['---', 'FIXED'],
            'keywords': 'meta',
            'keywords_type': 'allwords',
            'short_desc': r'(\[meta\]|\[tracking\])',
            'short_desc_type': 'notregexp',
            'f1': 'days_elapsed',
            'o1': 'lessthan',
            'v1': days_lookup,
            'product': self.products,
        }


if __name__ == '__main__':
    MetaSummaryMissing().run()
