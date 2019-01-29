# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from auto_nag.escalation import Escalation
from auto_nag.people import People


class TestEscalation(unittest.TestCase):

    config = {
        'high': {
            '[30;+∞[': {'supervisor': 'foobar', 'days': ['Thu']},
            '[20;30[': {'supervisor': 'n+1', 'days': ['Thu']},
            '[15;20[': {'supervisor': 'n+2', 'days': ['Mon', 'Thu']},
            '[5;15[': {'supervisor': 'director', 'days': ['Mon', 'Thu']},
            '[0;5[': {'supervisor': 'vp', 'days': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']},
        },
        'normal': {
            '[15;+∞[': {'supervisor': 'n+1', 'days': ['Thu']},
            '[10;15[': {'supervisor': 'n+2', 'days': ['Mon', 'Thu']},
            '[3;10[': {'supervisor': 'director', 'days': ['Mon', 'Thu']},
            '[0;3[': {'supervisor': 'vp', 'days': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']},
        },
        'default': {'[0;+∞[': {'supervisor': 'n+1', 'days': ['Mon']}},
    }

    def test_str(self):
        e = Escalation({}, data=TestEscalation.config)
        high = e.as_string('high').split('\n')
        assert high == [
            "[0;5[ => supervisor: vp, days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']",
            "[5;15[ => supervisor: director, days: ['Mon', 'Thu']",
            "[15;20[ => supervisor: n+2, days: ['Mon', 'Thu']",
            "[20;30[ => supervisor: n+1, days: ['Thu']",
            "[30;+∞[ => supervisor: foobar, days: ['Thu']",
        ]

        normal = e.as_string('normal').split('\n')
        assert normal == [
            "[0;3[ => supervisor: vp, days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']",
            "[3;10[ => supervisor: director, days: ['Mon', 'Thu']",
            "[10;15[ => supervisor: n+2, days: ['Mon', 'Thu']",
            "[15;+∞[ => supervisor: n+1, days: ['Thu']",
        ]

        default = e.as_string('default').split('\n')
        assert default == ["[0;+∞[ => supervisor: n+1, days: ['Mon']"]

    def test_escalation(self):
        people = [
            {
                'mail': 'a.b@mozilla.com',
                'cn': 'A B',
                'ismanager': 'FALSE',
                'manager': {'dn': 'mail=c.d@mozilla.com,o=org,dc=mozilla'},
                'title': 'nothing',
            },
            {
                'mail': 'c.d@mozilla.com',
                'cn': 'C D',
                'ismanager': 'TRUE',
                'manager': {'dn': 'mail=e.f@mozilla.com,o=org,dc=mozilla'},
                'title': 'manager',
            },
            {
                'mail': 'e.f@mozilla.com',
                'cn': 'E F',
                'ismanager': 'TRUE',
                'manager': {'dn': 'mail=g.h@mozilla.com,o=org,dc=mozilla'},
                'title': 'super manager',
            },
            {
                'mail': 'g.h@mozilla.com',
                'cn': 'G H',
                'ismanager': 'TRUE',
                'manager': {'dn': 'mail=i.j@mozilla.com,o=org,dc=mozilla'},
                'title': 'super manager',
            },
            {
                'mail': 'i.j@mozilla.com',
                'cn': 'I J',
                'ismanager': 'TRUE',
                'manager': {'dn': 'mail=k.l@mozilla.com,o=org,dc=mozilla'},
                'title': 'director',
            },
            {
                'mail': 'k.l@mozilla.com',
                'cn': 'K L',
                'ismanager': 'TRUE',
                'title': 'vice president',
            },
        ]

        e = Escalation(People(people), data=TestEscalation.config)
        assert e.get_supervisor('high', 35, 'a.b@mozilla.com', foobar='foobar@mozilla.com') == 'foobar@mozilla.com'
        assert e.get_supervisor('high', 25, 'a.b@mozilla.com') == 'c.d@mozilla.com'
        assert e.get_supervisor('high', 20, 'a.b@mozilla.com') == 'c.d@mozilla.com'
        assert e.get_supervisor('high', 18, 'a.b@mozilla.com') == 'e.f@mozilla.com'
        assert e.get_supervisor('high', 7, 'a.b@mozilla.com') == 'i.j@mozilla.com'
        assert e.get_supervisor('high', 1, 'a.b@mozilla.com') == 'k.l@mozilla.com'

        assert e.filter('high', 25, 0) == False
        assert e.filter('high', 25, 3) == True
        assert e.filter('high', 18, 0) == True
        assert e.filter('high', 18, 1) == False
        assert e.filter('high', 18, 3) == True
        assert e.filter('high', 18, 5) == False
        assert e.filter('high', 7, 1) == False
        assert e.filter('high', 7, 3) == True
        assert e.filter('high', 7, 5) == False
        assert e.filter('high', 1, 1) == True
        assert e.filter('high', 1, 3) == True
        assert e.filter('high', 1, 4) == True
        assert e.filter('high', 7, 5) == False

        assert e.get_supervisor('normal', 17, 'a.b@mozilla.com') == 'c.d@mozilla.com'
        assert e.get_supervisor('normal', 15, 'a.b@mozilla.com') == 'c.d@mozilla.com'
        assert e.get_supervisor('normal', 12, 'a.b@mozilla.com') == 'e.f@mozilla.com'
        assert e.get_supervisor('normal', 7, 'a.b@mozilla.com') == 'i.j@mozilla.com'
        assert e.get_supervisor('normal', 1, 'a.b@mozilla.com') == 'k.l@mozilla.com'

        assert e.get_supervisor('default', 17, 'a.b@mozilla.com') == 'c.d@mozilla.com'
        assert e.get_supervisor('default', 7, 'a.b@mozilla.com') == 'c.d@mozilla.com'
        assert e.get_supervisor('default', 1, 'a.b@mozilla.com') == 'c.d@mozilla.com'
        assert e.get_supervisor('default', 0, 'a.b@mozilla.com') == 'c.d@mozilla.com'
