# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from libmozdata import versions as lmdversions

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.rules.regression_set_status_flags import RegressionSetStatusFlags


def _mock_get_checked_versions(base=True):
    return {
        "release": 2,
        "beta": 3,
        "nightly": 4,
        "central": 4,
        "esr": 3,
        "esr_previous": 2,
    }


def _mock_get_bugs(self, *args, **kwargs):
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


def _mock_get_flags_from_regressing_bugs(self, bugids):
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


@pytest.fixture
def regression_set_status_flags_patches(monkeypatch):
    monkeypatch.setattr(utils, "get_checked_versions", _mock_get_checked_versions)
    monkeypatch.setattr(lmdversions, "get", _mock_get_checked_versions)
    monkeypatch.setattr(BzCleaner, "get_bugs", _mock_get_bugs)
    monkeypatch.setattr(
        RegressionSetStatusFlags,
        "get_flags_from_regressing_bugs",
        _mock_get_flags_from_regressing_bugs,
    )


def test_status_changes(regression_set_status_flags_patches):
    r = RegressionSetStatusFlags()
    bugs = r.get_bugs()
    assert sorted(bugs) == ["1111", "2222", "3333"]
    assert list(r.status_changes) == ["1111", "2222", "3333"]
    assert sorted(r.status_changes["1111"]) == [
        "cf_status_firefox2",
        "cf_status_firefox_esr2",
        "cf_status_firefox_esr3",
        "comment",
        "keywords",
    ]
    assert sorted(r.status_changes["1111"]["comment"]) == [
        "body",
        "is_private",
    ]
    assert r.status_changes["1111"]["cf_status_firefox2"] == "unaffected"
    assert r.status_changes["1111"]["cf_status_firefox_esr2"] == "unaffected"
    assert r.status_changes["1111"]["cf_status_firefox_esr3"] == "affected"
    assert not r.status_changes["1111"]["comment"]["is_private"]
    assert r.status_changes["3333"]["comment"]["is_private"]
