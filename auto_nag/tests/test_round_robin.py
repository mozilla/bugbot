# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest
from mock import patch

from auto_nag.round_robin import BadFallback, RoundRobin


class TestRoundRobin(unittest.TestCase):

    config = {
        'doc': 'The triagers need to have a \'Fallback\' entry.',
        'triagers': {
            'A B': {'bzmail': 'ab@mozilla.com'},
            'C D': {'bzmail': 'cd@mozilla.com'},
            'E F': {'bzmail': 'ef@mozilla.com'},
            'Fallback': {'bzmail': 'gh@mozilla.com'},
        },
        'components': {'P1::C1': 'default', 'P2::C2': 'default', 'P3::C3': 'special'},
        'default': {
            'doc': 'All the dates are the duty end dates.',
            '2019-02-21': 'A B',
            '2019-02-28': 'C D',
            '2019-03-07': 'E F',
        },
        'special': {
            'doc': 'All the dates are the duty end dates.',
            '2019-02-21': 'E F',
            '2019-02-28': 'A B',
            '2019-03-07': 'C D',
        },
    }

    def mk_bug(self, pc):
        p, c = pc.split('::')
        return {
            'product': p,
            'component': c,
            'triage_owner': 'ij@mozilla.com',
            'triage_owner_detail': {'nick': 'ij'},
        }

    @staticmethod
    def _get_nick(x, bzmail):
        return bzmail.split('@')[0]

    def test_get(self):
        with patch.object(RoundRobin, 'get_nick', new=TestRoundRobin._get_nick):
            rr = RoundRobin(rr={'team': TestRoundRobin.config})

            assert rr.get(self.mk_bug('P1::C1'), '2019-02-17') == (
                'ab@mozilla.com',
                'ab',
            )
            assert rr.get(self.mk_bug('P2::C2'), '2019-02-17') == (
                'ab@mozilla.com',
                'ab',
            )
            assert rr.get(self.mk_bug('P3::C3'), '2019-02-17') == (
                'ef@mozilla.com',
                'ef',
            )

            assert rr.get(self.mk_bug('P1::C1'), '2019-02-24') == (
                'cd@mozilla.com',
                'cd',
            )
            assert rr.get(self.mk_bug('P2::C2'), '2019-02-24') == (
                'cd@mozilla.com',
                'cd',
            )
            assert rr.get(self.mk_bug('P3::C3'), '2019-02-24') == (
                'ab@mozilla.com',
                'ab',
            )

            assert rr.get(self.mk_bug('P1::C1'), '2019-02-28') == (
                'cd@mozilla.com',
                'cd',
            )
            assert rr.get(self.mk_bug('P2::C2'), '2019-02-28') == (
                'cd@mozilla.com',
                'cd',
            )
            assert rr.get(self.mk_bug('P3::C3'), '2019-02-28') == (
                'ab@mozilla.com',
                'ab',
            )

            assert rr.get(self.mk_bug('P1::C1'), '2019-03-05') == (
                'ef@mozilla.com',
                'ef',
            )
            assert rr.get(self.mk_bug('P2::C2'), '2019-03-05') == (
                'ef@mozilla.com',
                'ef',
            )
            assert rr.get(self.mk_bug('P3::C3'), '2019-03-05') == (
                'cd@mozilla.com',
                'cd',
            )

            assert rr.get(self.mk_bug('P1::C1'), '2019-03-08') == (
                'gh@mozilla.com',
                'gh',
            )
            assert rr.get(self.mk_bug('P2::C2'), '2019-03-08') == (
                'gh@mozilla.com',
                'gh',
            )
            assert rr.get(self.mk_bug('P3::C3'), '2019-03-08') == (
                'gh@mozilla.com',
                'gh',
            )

            assert rr.get(self.mk_bug('Foo::Bar'), '2019-03-01') == (
                'ij@mozilla.com',
                'ij',
            )

    def test_get_who_to_nag(self):
        with patch.object(RoundRobin, 'is_mozilla', return_value=True):
            rr = RoundRobin(rr={'team': TestRoundRobin.config})

            assert rr.get_who_to_nag('2019-02-25') == {}
            assert rr.get_who_to_nag('2019-02-28') == {'gh@mozilla.com': ['']}
            assert rr.get_who_to_nag('2019-03-05') == {'gh@mozilla.com': ['']}
            assert rr.get_who_to_nag('2019-03-07') == {'gh@mozilla.com': ['']}
            assert rr.get_who_to_nag('2019-03-10') == {'gh@mozilla.com': ['']}

        with patch.object(RoundRobin, 'is_mozilla', return_value=False):
            rr = RoundRobin(rr={'team': TestRoundRobin.config})

            self.assertRaises(BadFallback, rr.get_who_to_nag, '2019-03-01')
