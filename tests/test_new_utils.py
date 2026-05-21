# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils


def test_get_signatures():
    s = " [@ abc]\n[@ def ]\r\n [@ ghi  ]  \r\n[@ jkl]   "
    s = utils.get_signatures(s)
    assert s == {"abc", "def", "ghi", "jkl"}


def test_add_signatures():
    old = "[@ x]\n[@ y]"
    new = " [@ abc]\n[@ def ]\r\n [@ ghi  ]  \r\n[@ jkl]   "
    new = utils.get_signatures(new)

    sgns = utils.add_signatures(old, new)
    assert sgns == "[@ x]\n[@ y]\n[@ abc]\n[@ def]\n[@ ghi]\n[@ jkl]"

    sgns = utils.add_signatures("", new)
    assert sgns == "[@ abc]\n[@ def]\n[@ ghi]\n[@ jkl]"
