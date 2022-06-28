# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import unittest

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.scripts.regression_set_status_flags import RegressionSetStatusFlags


def mock_get_checked_versions():
    return {
        "release": 2,
        "beta": 3,
        "nightly": 4,
        "central": 4,
        "esr": 3,
        "esr_previous": 2,
    }


def mock_get_bugs(self, *args, **kwargs):
    return {
        "1111": {
            "id": 1111,
            "cf_status_firefox_esr2": "---",
            "cf_status_firefox_esr3": "---",
            "cf_status_firefox2": "---",
            "cf_status_firefox3": "affected",
            "cf_status_firefox4": "fixed",
            "regressed_by": 111,
        },
        "2222": {
            "id": 2222,
            "cf_status_firefox_esr2": "---",
            "cf_status_firefox_esr3": "---",
            "cf_status_firefox2": "---",
            "cf_status_firefox3": "---",
            "cf_status_firefox4": "---",
            "regressed_by": 222,
        },
        "3333": {
            "id": 3333,
            "cf_status_firefox_esr2": "---",
            "cf_status_firefox_esr3": "---",
            "cf_status_firefox2": "---",
            "cf_status_firefox3": "affected",
            "cf_status_firefox4": "fixed",
            "regressed_by": 333,
        },
    }


def mock_get_flags_from_regressing_bugs(self, bugids):
    assert sorted(bugids) == [111, 222, 333]
    return {
        111: {
            "id": 111,
            "cf_status_firefox_esr3": "fixed",
            "cf_status_firefox3": "fixed",
        },
        222: {
            "id": 222,
            "cf_status_firefox1": "fixed",
        },
        333: {
            "id": 333,
            "cf_status_firefox_esr3": "fixed",
            "cf_status_firefox3": "fixed",
            "groups": ["core-security-release"],
        },
    }


class TestSetStatusFlags(unittest.TestCase):
    def setUp(self):
        self.orig_get_checked_versions = utils.get_checked_versions
        self.orig_get_bugs = BzCleaner.get_bugs
        self.orig_get_flags_from_regressing_bugs = (
            RegressionSetStatusFlags.get_flags_from_regressing_bugs
        )
        utils.get_checked_versions = mock_get_checked_versions
        BzCleaner.get_bugs = mock_get_bugs
        RegressionSetStatusFlags.get_flags_from_regressing_bugs = (
            mock_get_flags_from_regressing_bugs
        )

    def tearDown(self):
        utils.get_checked_versions = self.orig_get_checked_versions
        BzCleaner.get_bugs = self.orig_get_bugs
        RegressionSetStatusFlags.get_flags_from_regressing_bugs = (
            self.orig_get_flags_from_regressing_bugs
        )

    def test_status_changes(self):
        r = RegressionSetStatusFlags()
        bugs = r.get_bugs()
        self.assertEqual(sorted(bugs), ["1111", "2222", "3333"])
        self.assertEqual(list(r.status_changes), ["1111", "2222", "3333"])
        self.assertEqual(
            sorted(r.status_changes["1111"]),
            [
                "cf_status_firefox2",
                "cf_status_firefox_esr2",
                "cf_status_firefox_esr3",
                "comment",
            ],
        )
        self.assertEqual(r.status_changes["1111"]["cf_status_firefox2"], "unaffected")
        self.assertEqual(
            r.status_changes["1111"]["cf_status_firefox_esr2"], "unaffected"
        )
        self.assertEqual(r.status_changes["1111"]["cf_status_firefox_esr3"], "affected")
        self.assertFalse(r.status_changes["1111"]["comment"]["is_private"])
        self.assertTrue(r.status_changes["3333"]["comment"]["is_private"])
