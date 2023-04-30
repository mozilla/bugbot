# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import unittest

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.rules.inactive_ni_pending import InactiveNeedinfoPending


class TestBZClearner(unittest.TestCase):
    def test_description(self):
        assert BzCleaner().description() == ""

    def test_name(self):
        assert BzCleaner().name() == "bzcleaner"

    def test_template(self):
        assert BzCleaner().template() == "bzcleaner.html"

    def test_subject(self):
        assert BzCleaner().subject() == ""

    def test_email_subject(self):
        assert "[bugbot]" in BzCleaner().get_email_subject(None)

    def test_ignore_date(self):
        self.assertFalse(BzCleaner().ignore_date())

    def test_has_individual_autofix(self):
        bzc = BzCleaner()
        changes = {"123": {}, "456": {}, 789: {}}
        self.assertTrue(bzc.has_individual_autofix(changes))
        changes = {"cc": ["foo@mozilla.com"], "comment": {"body": "hello"}}
        self.assertFalse(bzc.has_individual_autofix(changes))


class TestBZClearnerClass(unittest.TestCase):
    def test_description(self):
        assert "Bugs with needinfo pending" in InactiveNeedinfoPending().description()

    def test_name(self):
        assert InactiveNeedinfoPending().name() == "inactive_ni_pending"

    def test_template(self):
        assert InactiveNeedinfoPending().template() == "inactive_ni_pending.html"

    def test_subject(self):
        assert "Bugs with needinfo pending" in InactiveNeedinfoPending().subject()

    def test_get_bz_params(self):
        rule = InactiveNeedinfoPending()
        if not rule.has_enough_data():
            # we've non-following versions in product-details
            # so cheat on versions.
            rule.versions = {"central": 1, "beta": 2, "release": 3}
            rule.status_release = utils.get_flag(
                rule.versions["release"], "status", "release"
            )
            rule.flags_map = {}

        p = rule.get_bz_params("today")
        assert p["o1"] == "equals"
        assert "flagtypes" in p["f1"]
        assert "type" in p["include_fields"]

    def test_ignore_date(self):
        self.assertFalse(InactiveNeedinfoPending().ignore_date())
