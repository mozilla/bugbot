# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from auto_nag.mail import replaceUnicode


class TestMail(unittest.TestCase):
    def test_replaceUnicode(self):
        s = "some letters and a é and a è, what else ?..."
        r = replaceUnicode(s)
        assert r == "some letters and a &#233; and a &#232;, what else ?..."

        s = "some letters and a é and a è"
        r = replaceUnicode(s)
        assert r == "some letters and a &#233; and a &#232;"

        s = "some letters with no accents, just pure ascii"
        r = replaceUnicode(s)
        assert r == s

        s = ""
        r = replaceUnicode(s)
        assert r == s
