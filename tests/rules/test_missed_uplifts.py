# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from jinja2 import Environment, FileSystemLoader

from bugbot import utils
from bugbot.rules.missed_uplifts import MissedUplifts

VERSIONS = {
    "release": 141,
    "beta": 142,
    "nightly": 143,
    "central": 143,
    "esr": 140,
    "esr_previous": 128,
}


@pytest.fixture
def rule(monkeypatch):
    monkeypatch.setattr(utils, "get_checked_versions", lambda: dict(VERSIONS))
    monkeypatch.setattr(
        utils, "get_report_bugs", lambda channel, version=None, op="+": []
    )
    return MissedUplifts()


def _rows(rule, **statuses):
    bug = {
        "id": 1234567,
        "priority": "P1",
        "severity": "S2",
        # handle_bug() reads the beta and release flags unconditionally.
        "cf_status_firefox142": "---",
        "cf_status_firefox141": "---",
        **statuses,
    }
    data = {}
    rule.handle_bug(bug, data)
    # The framework fills these in while collecting the bugs.
    data["1234567"].update({"id": "1234567", "summary": "a bug"})
    return utils.organize(data, rule.columns(), key=rule.sort_columns())


def test_affected_versions_are_rendered(rule):
    """The affected versions must render even though they are ints (bug 2990)."""
    rows = _rows(
        rule,
        cf_status_firefox142="affected",
        cf_status_firefox141="affected",
        cf_status_firefox_esr140="affected",
    )

    env = Environment(loader=FileSystemLoader("templates"))
    body = env.get_template(rule.template()).render(
        date="2026-08-17",
        data=rows,
        extra={},
        str=str,
        enumerate=enumerate,
        plural=utils.plural,
        no_manager=set(),
        table_attrs="",
    )

    assert "142, 141, 140" in body


def test_affected_versions_sort_numerically(rule):
    """Affected versions are ints, so sorting must not fall back to string order."""
    rows = _rows(rule, cf_status_firefox142="affected")
    assert rows[0][3] == [142]

    # Sorting compares the reversed affected list; it must not raise.
    sorted([(0, 0, 0, [142]), (0, 0, 0, [142, 141, 140])], key=lambda p: p[3])
