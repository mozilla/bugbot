# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class FeatureRegression(BzCleaner):

    def __init__(self):
        super(FeatureRegression, self).__init__()

    def description(self):
        return 'Get the top crashes bug without a proper severity'

    def name(self):
        return 'feature_regression'

    def template(self):
        return 'feature_regression.html'

    def subject(self):
        return 'Bugs with feature and regression keywords'

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        return {'resolution': ['---', 'FIXED'],
                'keywords': ['feature', 'regression'],
                'keywords_type': 'allwords'}


if __name__ == '__main__':
    FeatureRegression().run()
