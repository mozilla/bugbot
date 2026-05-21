# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import csv
from typing import List
from unittest.mock import patch

import pytest

from bugbot.people import People
from bugbot.round_robin import RotationDefinitions, RoundRobin
from bugbot.round_robin_calendar import BadFallback


class RotationDefinitionsMockup(RotationDefinitions):
    def __init__(self, csv_lines: List[str]) -> None:
        self.csv_lines = csv_lines

    def get_definitions_records(self):
        return csv.DictReader(self.csv_lines)


@pytest.fixture
def round_robin_config():
    return RotationDefinitionsMockup(
        [
            "Team Name,Calendar Scope,Fallback Triager,Calendar URL",
            "team,P1::C1,G H,tests/data/calendar_default.json",
            "team,P2::C2,G H,tests/data/calendar_default.json",
            "team,P3::C3,G H,tests/data/calendar_special.json",
        ]
    )


@pytest.fixture
def round_robin_config_ics():
    return RotationDefinitionsMockup(
        [
            "Team Name,Calendar Scope,Fallback Triager,Calendar URL",
            "team,P1::C1,G H,tests/data/calendar.ics",
            "team,P2::C2,G H,tests/data/calendar.ics",
        ]
    )


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


def _get_nick(x, bzmail, pc, cal):
    return bzmail.split("@")[0]


def test_get(round_robin_config, round_robin_people, mk_bug):
    with patch.object(RoundRobin, "get_nick", new=_get_nick):
        rr = RoundRobin(
            rotation_definitions=round_robin_config, people=round_robin_people
        )

        assert rr.get(mk_bug("P1::C1"), "2019-02-17") == ("ab@mozilla.com", "ab")
        assert rr.get(mk_bug("P2::C2"), "2019-02-17") == ("ab@mozilla.com", "ab")
        assert rr.get(mk_bug("P3::C3"), "2019-02-17") == ("ef@mozilla.com", "ef")

        assert rr.get(mk_bug("P1::C1"), "2019-02-24") == ("cd@mozilla.com", "cd")
        assert rr.get(mk_bug("P2::C2"), "2019-02-24") == ("cd@mozilla.com", "cd")
        assert rr.get(mk_bug("P3::C3"), "2019-02-24") == ("ab@mozilla.com", "ab")

        assert rr.get(mk_bug("P1::C1"), "2019-02-28") == ("ef@mozilla.com", "ef")
        assert rr.get(mk_bug("P2::C2"), "2019-02-28") == ("ef@mozilla.com", "ef")
        assert rr.get(mk_bug("P3::C3"), "2019-02-28") == ("cd@mozilla.com", "cd")

        assert rr.get(mk_bug("P1::C1"), "2019-03-05") == ("ef@mozilla.com", "ef")
        assert rr.get(mk_bug("P2::C2"), "2019-03-05") == ("ef@mozilla.com", "ef")
        assert rr.get(mk_bug("P3::C3"), "2019-03-05") == ("cd@mozilla.com", "cd")

        assert rr.get(mk_bug("P1::C1"), "2019-03-08") == ("gh@mozilla.com", "gh")
        assert rr.get(mk_bug("P2::C2"), "2019-03-08") == ("gh@mozilla.com", "gh")
        assert rr.get(mk_bug("P3::C3"), "2019-03-08") == ("gh@mozilla.com", "gh")

        assert rr.get(mk_bug("Foo::Bar"), "2019-03-01") == ("ij@mozilla.com", "ij")


def test_get_ics(round_robin_config_ics, round_robin_people, mk_bug):
    with patch.object(RoundRobin, "get_nick", new=_get_nick):
        rr = RoundRobin(
            rotation_definitions=round_robin_config_ics,
            people=round_robin_people,
        )

        assert rr.get(mk_bug("P1::C1"), "2019-02-17") == ("ab@mozilla.com", "ab")
        assert rr.get(mk_bug("P2::C2"), "2019-02-17") == ("ab@mozilla.com", "ab")

        assert rr.get(mk_bug("P1::C1"), "2019-02-24") == ("cd@mozilla.com", "cd")
        assert rr.get(mk_bug("P2::C2"), "2019-02-24") == ("cd@mozilla.com", "cd")

        assert rr.get(mk_bug("P1::C1"), "2019-02-28") == ("ef@mozilla.com", "ef")
        assert rr.get(mk_bug("P2::C2"), "2019-02-28") == ("ef@mozilla.com", "ef")

        assert rr.get(mk_bug("P1::C1"), "2019-03-05") == ("ef@mozilla.com", "ef")
        assert rr.get(mk_bug("P2::C2"), "2019-03-05") == ("ef@mozilla.com", "ef")

        assert rr.get(mk_bug("P1::C1"), "2019-03-08") == ("ab@mozilla.com", "ab")
        assert rr.get(mk_bug("P2::C2"), "2019-03-08") == ("ab@mozilla.com", "ab")

        assert rr.get(mk_bug("P1::C1"), "2019-03-15") == ("gh@mozilla.com", "gh")
        assert rr.get(mk_bug("P2::C2"), "2019-03-15") == ("gh@mozilla.com", "gh")

        assert rr.get(mk_bug("Foo::Bar"), "2019-03-01") == ("ij@mozilla.com", "ij")


def test_get_who_to_nag(round_robin_config, round_robin_people):
    rr = RoundRobin(rotation_definitions=round_robin_config, people=round_robin_people)

    empty = {"team": {"nobody": True, "persons": []}}

    assert rr.get_who_to_nag("2019-02-25") == {}
    assert rr.get_who_to_nag("2019-03-01") == {"gh@mozilla.com": empty}
    assert rr.get_who_to_nag("2019-03-05") == {"gh@mozilla.com": empty}
    assert rr.get_who_to_nag("2019-03-07") == {"gh@mozilla.com": empty}
    assert rr.get_who_to_nag("2019-03-10") == {"gh@mozilla.com": empty}

    with patch.object(People, "get_moz_mail", return_value=None):
        rr = RoundRobin(
            rotation_definitions=round_robin_config, people=round_robin_people
        )

        with pytest.raises(BadFallback):
            rr.get_who_to_nag("2019-03-01")
