# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.rules.inactive_ni_pending import InactiveNeedinfoPending


def test_description():
    assert BzCleaner().description() == ""


def test_name():
    assert BzCleaner().name() == "bzcleaner"


def test_template():
    assert BzCleaner().template() == "bzcleaner.html"


def test_subject():
    assert BzCleaner().subject() == ""


def test_email_subject():
    assert "[bugbot]" in BzCleaner().get_email_subject(None)


def test_ignore_date():
    assert not BzCleaner().ignore_date()


def test_has_individual_autofix():
    bzc = BzCleaner()
    changes = {"123": {}, "456": {}, 789: {}}
    assert bzc.has_individual_autofix(changes)
    changes = {"cc": ["foo@mozilla.com"], "comment": {"body": "hello"}}
    assert not bzc.has_individual_autofix(changes)


def test_inactive_needinfo_description():
    assert "Bugs with needinfo pending" in InactiveNeedinfoPending().description()


def test_inactive_needinfo_name():
    assert InactiveNeedinfoPending().name() == "inactive_ni_pending"


def test_inactive_needinfo_template():
    assert InactiveNeedinfoPending().template() == "inactive_ni_pending.html"


def test_inactive_needinfo_subject():
    assert "Bugs with needinfo pending" in InactiveNeedinfoPending().subject()


def test_inactive_needinfo_get_bz_params():
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


def test_inactive_needinfo_ignore_date():
    assert not InactiveNeedinfoPending().ignore_date()
