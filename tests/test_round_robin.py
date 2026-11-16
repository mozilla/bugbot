# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import csv
from unittest.mock import patch

import pytest

from bugbot.people import People
from bugbot.round_robin import RotationDefinitions, RoundRobin


class RotationDefinitionsMockup(RotationDefinitions):
    def __init__(self, csv_lines: list[str]) -> None:
        self.csv_lines = csv_lines

    def get_definitions_records(self):
        return csv.DictReader(
            self.csv_lines,
            fieldnames=[
                "Team Name",
                "Calendar Scope",
                "Fallback Triager",
                "Calendar URL",
            ],
        )


@pytest.fixture
def round_robin_config():
    return [
        "team,P1::C1,G H,tests/data/calendar_default.json",
        "team,P2::C2,G H,tests/data/calendar_default.json",
        "team,P3::C3,G H,tests/data/calendar_special.json",
    ]


@pytest.fixture
def round_robin_people():
    return People(
        [
            {
                "mail": "{}{}@mozilla.com".format(x, y),
                "cn": "{} {}".format(x.upper(), y.upper()),
                "ismanager": "FALSE",
                "title": "nothing",
                # Dummy info to satisfy the Person type
                "bugzillaEmail": "",
                "bugzillaID": "",
                "dn": "mail=xx@mozilla.com,o=com,dc=mozilla",
                "found_on_bugzilla": True,
                "im": [],
                "isdirector": "FALSE",
                "manager": {"cn": "", "dn": "mail=xxx@mozilla.com,o=com,dc=mozilla"},
            }
            for x, y in zip("aceg", "bdfh")
        ]
    )


@pytest.fixture
def mk_bug():
    def _mk(pc):
        p, c = pc.split("::")
        return {
            "product": p,
            "component": c,
            "triage_owner": "ij@mozilla.com",
            "triage_owner_detail": {"nick": "ij"},
        }

    return _mk


@pytest.fixture
def make_round_robin(round_robin_people, monkeypatch):
    def get_nick(self, bzmail, prod_comp, cal):
        return bzmail.split("@")[0]

    monkeypatch.setattr(RoundRobin, "get_nick", get_nick)

    def make(rows):
        return RoundRobin(
            rotation_definitions=RotationDefinitionsMockup(rows),
            people=round_robin_people,
        )

    return make


@pytest.mark.parametrize(
    "calendar, rotations",
    [
        (
            "calendar_default.json",
            [
                ("2019-02-17", "ab"),
                ("2019-02-24", "cd"),
                ("2019-02-28", "ef"),
                ("2019-03-05", "ef"),
                ("2019-03-08", "gh"),
            ],
        ),
        (
            "calendar_special.json",
            [
                ("2019-02-17", "ef"),
                ("2019-02-24", "ab"),
                ("2019-02-28", "cd"),
                ("2019-03-05", "cd"),
                ("2019-03-08", "gh"),
            ],
        ),
        (
            "calendar.ics",
            [
                ("2019-02-17", "ab"),
                ("2019-02-24", "cd"),
                ("2019-02-28", "ef"),
                ("2019-03-05", "ef"),
                ("2019-03-08", "ab"),
                ("2019-03-15", "gh"),
            ],
        ),
    ],
)
def test_get(calendar, rotations, make_round_robin, mk_bug):
    components = ["P1::C1", "P2::C2"]
    rr = make_round_robin(
        [f"team,{component},G H,tests/data/{calendar}" for component in components]
    )

    for date, nick in rotations:
        for component in components:
            assert rr.get(mk_bug(component), date) == (f"{nick}@mozilla.com", nick)

    assert rr.get(mk_bug("Foo::Bar"), "2019-03-01") == ("ij@mozilla.com", "ij")


def test_get_who_to_nag(round_robin_config, make_round_robin):
    rr = make_round_robin(round_robin_config)

    assert rr.get_who_to_nag("2019-02-25") == {}
    for date in ("2019-03-01", "2019-03-05", "2019-03-07", "2019-03-10"):
        assert rr.get_who_to_nag(date) == {
            "gh@mozilla.com": {"team": {"nobody": True, "persons": []}}
        }


def test_missing_fallback_mozmail(round_robin_config, make_round_robin):
    with patch.object(People, "get_moz_mail", return_value=None):
        rr = make_round_robin(round_robin_config)

    assert rr.get_components() == []
    assert rr.get_who_to_nag("2019-03-01") == {}


@pytest.mark.parametrize("bad_team", ["good", "bad"])
def test_invalid_fallback_only_disables_its_calendar(
    bad_team, make_round_robin, mk_bug
):
    rr = make_round_robin(
        [
            "good,P1::C1,G H,tests/data/calendar_default.json",
            f"{bad_team},P2::C2,X Y,tests/data/calendar_special.json",
            f"{bad_team},P3::C3,X Y,tests/data/calendar_special.json",
            "good,P4::C4,G H,tests/data/calendar_default.json",
        ]
    )

    assert sorted(rr.get_components()) == ["P1::C1", "P4::C4"]

    # Valid calendars still rotate and use their fallback when empty.
    for component in ("P1::C1", "P4::C4"):
        assert rr.get(mk_bug(component), "2019-02-17") == ("ab@mozilla.com", "ab")
        assert rr.get(mk_bug(component), "2019-03-08") == ("gh@mozilla.com", "gh")

    # Disabled components use the Bugzilla triage owner.
    for component in ("P2::C2", "P3::C3"):
        for date in ("2019-02-17", "2019-03-08"):
            assert rr.get(mk_bug(component), date) == ("ij@mozilla.com", "ij")

    assert rr.get_who_to_nag("2019-03-01") == {
        "gh@mozilla.com": {"good": {"nobody": True, "persons": []}}
    }
