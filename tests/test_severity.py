# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.severity import Severity


def test_logical_comparison():
    assert Severity("--") == Severity("N/A")
    assert not Severity("--") > Severity("N/A")
    assert not Severity("--") < Severity("N/A")

    assert Severity("S1") > Severity("S2")
    assert not Severity("S1") == Severity("S2")
    assert not Severity("S1") < Severity("S2")

    assert Severity("S2") > Severity("S3")
    assert Severity("S4") > Severity("--")
    assert Severity("S4") > Severity("N/A")
