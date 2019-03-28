# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class HasRegressionRange(BzCleaner):
    def __init__(self):
        super(HasRegressionRange, self).__init__()

    def description(self):
        return 'Get the closed bugs with has-regression-range without the regression keyword'

    def name(self):
        return 'has_reg_range'

    def template(self):
        return 'has_reg_range.html'

    def subject(self):
        return 'Bugs with has_regression_range=yes but no regression keyword'

    def has_default_products(self):
        return False

    def get_bz_params(self, date):
        params = {
            'f1': 'keywords',
            'o1': 'nowords',
            'v1': 'regression',
            'f2': 'cf_has_regression_range',
            'o2': 'equals',
            'v2': 'yes',
        }

        return params

    def get_autofix_change(self):
        return {'keywords': {'add': ['regression']}}


if __name__ == '__main__':
    HasRegressionRange().run()
