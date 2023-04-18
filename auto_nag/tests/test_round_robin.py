# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import csv
import unittest
from typing import List
from unittest.mock import patch

from auto_nag.people import People
from auto_nag.round_robin import RotationDefinitions, RoundRobin
from auto_nag.round_robin_calendar import BadFallback


class RotationDefinitionsMockup(RotationDefinitions):
    def __init__(self, csv_lines: List[str]) -> None:
        self.csv_lines = csv_lines

    def get_definitions_records(self):
        return csv.DictReader(self.csv_lines)


class TestRoundRobin(unittest.TestCase):

    config = RotationDefinitionsMockup(
        [
            "Team Name,Calendar Scope,Fallback Triager,Calendar URL",
            "team,P1::C1,G H,auto_nag/tests/data/calendar_default.json",
            "team,P2::C2,G H,auto_nag/tests/data/calendar_default.json",
            "team,P3::C3,G H,auto_nag/tests/data/calendar_special.json",
        ]
    )

    config_ics = RotationDefinitionsMockup(
        [
            "Team Name,Calendar Scope,Fallback Triager,Calendar URL",
            "team,P1::C1,G H,auto_nag/tests/data/calendar.ics",
            "team,P2::C2,G H,auto_nag/tests/data/calendar.ics",
        ]
    )

    people = People(
        [
            {
                "mail": "{}{}@mozilla.com".format(x, y),
                "cn": "{} {}".format(x.upper(), y.upper()),
                "ismanager": "FALSE",
                "title": "nothing",
            }
            for x, y in zip("aceg", "bdfh")
        ]
    )

    def mk_bug(self, pc):
        p, c = pc.split("::")
        return {
            "product": p,
            "component": c,
            "triage_owner": "ij@mozilla.com",
            "triage_owner_detail": {"nick": "ij"},
        }

    @staticmethod
    def _get_nick(x, bzmail, pc, cal):
        return bzmail.split("@")[0]

    def test_get(self):
        with patch.object(RoundRobin, "get_nick", new=TestRoundRobin._get_nick):
            rr = RoundRobin(
                rotation_definitions=TestRoundRobin.config, people=TestRoundRobin.people
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-02-17") == (
                "ab@mozilla.com",
                "ab",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-02-17") == (
                "ab@mozilla.com",
                "ab",
            )
            assert rr.get(self.mk_bug("P3::C3"), "2019-02-17") == (
                "ef@mozilla.com",
                "ef",
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-02-24") == (
                "cd@mozilla.com",
                "cd",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-02-24") == (
                "cd@mozilla.com",
                "cd",
            )
            assert rr.get(self.mk_bug("P3::C3"), "2019-02-24") == (
                "ab@mozilla.com",
                "ab",
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-02-28") == (
                "ef@mozilla.com",
                "ef",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-02-28") == (
                "ef@mozilla.com",
                "ef",
            )
            assert rr.get(self.mk_bug("P3::C3"), "2019-02-28") == (
                "cd@mozilla.com",
                "cd",
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-03-05") == (
                "ef@mozilla.com",
                "ef",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-03-05") == (
                "ef@mozilla.com",
                "ef",
            )
            assert rr.get(self.mk_bug("P3::C3"), "2019-03-05") == (
                "cd@mozilla.com",
                "cd",
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-03-08") == (
                "gh@mozilla.com",
                "gh",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-03-08") == (
                "gh@mozilla.com",
                "gh",
            )
            assert rr.get(self.mk_bug("P3::C3"), "2019-03-08") == (
                "gh@mozilla.com",
                "gh",
            )

            assert rr.get(self.mk_bug("Foo::Bar"), "2019-03-01") == (
                "ij@mozilla.com",
                "ij",
            )

    def test_get_ics(self):
        with patch.object(RoundRobin, "get_nick", new=TestRoundRobin._get_nick):
            rr = RoundRobin(
                rotation_definitions=TestRoundRobin.config_ics,
                people=TestRoundRobin.people,
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-02-17") == (
                "ab@mozilla.com",
                "ab",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-02-17") == (
                "ab@mozilla.com",
                "ab",
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-02-24") == (
                "cd@mozilla.com",
                "cd",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-02-24") == (
                "cd@mozilla.com",
                "cd",
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-02-28") == (
                "ef@mozilla.com",
                "ef",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-02-28") == (
                "ef@mozilla.com",
                "ef",
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-03-05") == (
                "ef@mozilla.com",
                "ef",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-03-05") == (
                "ef@mozilla.com",
                "ef",
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-03-08") == (
                "ab@mozilla.com",
                "ab",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-03-08") == (
                "ab@mozilla.com",
                "ab",
            )

            assert rr.get(self.mk_bug("P1::C1"), "2019-03-15") == (
                "gh@mozilla.com",
                "gh",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-03-15") == (
                "gh@mozilla.com",
                "gh",
            )

            assert rr.get(self.mk_bug("Foo::Bar"), "2019-03-01") == (
                "ij@mozilla.com",
                "ij",
            )

    def test_get_who_to_nag(self):
        rr = RoundRobin(
            rotation_definitions=TestRoundRobin.config, people=TestRoundRobin.people
        )

        empty = {"team": {"nobody": True, "persons": []}}

        assert rr.get_who_to_nag("2019-02-25") == {}
        assert rr.get_who_to_nag("2019-03-01") == {"gh@mozilla.com": empty}
        assert rr.get_who_to_nag("2019-03-05") == {"gh@mozilla.com": empty}
        assert rr.get_who_to_nag("2019-03-07") == {"gh@mozilla.com": empty}
        assert rr.get_who_to_nag("2019-03-10") == {"gh@mozilla.com": empty}

        with patch.object(People, "get_moz_mail", return_value=None):
            rr = RoundRobin(
                rotation_definitions=TestRoundRobin.config, people=TestRoundRobin.people
            )

            self.assertRaises(BadFallback, rr.get_who_to_nag, "2019-03-01")
