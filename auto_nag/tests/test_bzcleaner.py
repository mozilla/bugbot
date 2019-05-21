# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import unittest

from auto_nag.bzcleaner import BzCleaner
from auto_nag.scripts.tracked_bad_severity import TrackedBadSeverity
from auto_nag import utils


class TestBZClearner(unittest.TestCase):
    def test_description(self):
        assert BzCleaner().description() == ''

    def test_name(self):
        assert BzCleaner().name() == 'bzcleaner'

    def test_template(self):
        assert BzCleaner().template() == 'bzcleaner.html'

    def test_subject(self):
        assert BzCleaner().subject() == ''

    def test_email_subject(self):
        assert '[autonag]' in BzCleaner().get_email_subject(None)

    def test_ignore_date(self):
        self.assertFalse(BzCleaner().ignore_date())

    def test_has_individual_autofix(self):
        bzc = BzCleaner()
        changes = {'123': {}, '456': {}, 789: {}}
        self.assertTrue(bzc.has_individual_autofix(changes))
        changes = {'cc': ['foo@mozilla.com'], 'comment': {'body': 'hello'}}
        self.assertFalse(bzc.has_individual_autofix(changes))


class TestBZClearnerClass(unittest.TestCase):
    def test_description(self):
        assert 'Bug tracked' in TrackedBadSeverity().description()

    def test_name(self):
        assert TrackedBadSeverity().name() == 'tracked_bad_severity'

    def test_template(self):
        assert TrackedBadSeverity().template() == 'tracked_bad_severity.html'

    def test_subject(self):
        assert 'Bug tracked' in TrackedBadSeverity().subject()

    def test_get_bz_params(self):
        tool = TrackedBadSeverity()
        if not tool.has_enough_data():
            # we've non-following versions in product-details
            # so cheat on versions.
            tool.versions = {'central': 1, 'beta': 2, 'release': 3}
            tool.status_release = utils.get_flag(
                tool.versions['release'], 'status', 'release'
            )

        p = tool.get_bz_params(None)
        assert p['f1'] == 'OP'
        assert 'cf_tracking_firefox' in p['f3']
        assert 'enhancement' in p['bug_severity']

    def test_ignore_date(self):
        self.assertTrue(TrackedBadSeverity().ignore_date())
