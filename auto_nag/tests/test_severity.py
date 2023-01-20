# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from auto_nag.severity import Severity


class TestSeverity(unittest.TestCase):
    def test_logical_comparison(self):
        self.assertTrue(Severity("--") == Severity("N/A"))
        self.assertFalse(Severity("--") > Severity("N/A"))
        self.assertFalse(Severity("--") < Severity("N/A"))

        self.assertTrue(Severity("S1") > Severity("S2"))
        self.assertFalse(Severity("S1") == Severity("S2"))
        self.assertFalse(Severity("S1") < Severity("S2"))

        self.assertGreater(Severity("S2"), Severity("S3"))
        self.assertGreater(Severity("S4"), Severity("--"))
        self.assertGreater(Severity("S4"), Severity("N/A"))
