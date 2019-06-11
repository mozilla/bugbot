# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import unittest
from unittest.mock import patch

from auto_nag.people import People
from auto_nag.round_robin import RoundRobin
from auto_nag.round_robin_calendar import BadFallback


class TestRoundRobin(unittest.TestCase):

    default = {
        "duty-start-dates": {
            "2019-02-14": "A B",
            "2019-02-21": "C D",
            "2019-02-28": "E F",
        }
    }

    special = {
        "duty-start-dates": {
            "2019-02-14": "E F",
            "2019-02-21": "A B",
            "2019-02-28": "C D",
        }
    }

    config = {
        "fallback": "G H",
        "components": {"P1::C1": "default", "P2::C2": "default", "P3::C3": "special"},
        "default": {"calendar": json.dumps(default)},
        "special": {"calendar": json.dumps(special)},
    }

    config_ics = {
        "fallback": "G H",
        "components": {"P1::C1": "default", "P2::C2": "default"},
        "default": {"calendar": "auto_nag/tests/calendar.ics"},
    }

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
    def _get_nick(x, bzmail):
        return bzmail.split("@")[0]

    def test_get(self):
        with patch.object(RoundRobin, "get_nick", new=TestRoundRobin._get_nick):
            rr = RoundRobin(
                rr={"team": TestRoundRobin.config}, people=TestRoundRobin.people
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
                rr={"team": TestRoundRobin.config_ics}, people=TestRoundRobin.people
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
                "gh@mozilla.com",
                "gh",
            )
            assert rr.get(self.mk_bug("P2::C2"), "2019-03-08") == (
                "gh@mozilla.com",
                "gh",
            )

            assert rr.get(self.mk_bug("Foo::Bar"), "2019-03-01") == (
                "ij@mozilla.com",
                "ij",
            )

    def test_get_who_to_nag(self):
        rr = RoundRobin(
            rr={"team": TestRoundRobin.config}, people=TestRoundRobin.people
        )

        empty = {"team": {"nobody": True, "persons": []}}

        assert rr.get_who_to_nag("2019-02-25") == {}
        assert rr.get_who_to_nag("2019-03-01") == {"gh@mozilla.com": empty}
        assert rr.get_who_to_nag("2019-03-05") == {"gh@mozilla.com": empty}
        assert rr.get_who_to_nag("2019-03-07") == {"gh@mozilla.com": empty}
        assert rr.get_who_to_nag("2019-03-10") == {"gh@mozilla.com": empty}

        with patch.object(People, "get_moz_mail", return_value=None):
            rr = RoundRobin(
                rr={"team": TestRoundRobin.config}, people=TestRoundRobin.people
            )

            self.assertRaises(BadFallback, rr.get_who_to_nag, "2019-03-01")
