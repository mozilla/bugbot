# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from bugbot.webcompat_priority import WebcompatPriority


class TestWebcompatPriority(unittest.TestCase):
    def test_logical_comparison(self):
        self.assertTrue(WebcompatPriority("--") == WebcompatPriority("?"))
        self.assertTrue(WebcompatPriority("--") == WebcompatPriority("revisit"))
        self.assertTrue(WebcompatPriority("--") == WebcompatPriority("-"))

        self.assertGreater(WebcompatPriority("P1"), WebcompatPriority("P2"))
        self.assertGreater(WebcompatPriority("P2"), WebcompatPriority("P3"))
        self.assertGreater(WebcompatPriority("P3"), WebcompatPriority("-"))
        self.assertGreater(WebcompatPriority("P3"), WebcompatPriority("--"))
        self.assertGreater(WebcompatPriority("P3"), WebcompatPriority("?"))
        self.assertGreater(WebcompatPriority("P3"), WebcompatPriority("revisit"))

        self.assertFalse(WebcompatPriority("--") > WebcompatPriority("-"))
        self.assertFalse(WebcompatPriority("--") < WebcompatPriority("-"))
        self.assertFalse(WebcompatPriority("P1") == WebcompatPriority("P2"))
        self.assertFalse(WebcompatPriority("P1") < WebcompatPriority("P2"))
