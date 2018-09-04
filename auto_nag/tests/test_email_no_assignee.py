# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from auto_nag.scripts.no_assignee import NoAssignee


class TestEmailNoAssignee(unittest.TestCase):

    def test_nobody(self):
        bugids = NoAssignee().get_bugs('2011-01-01', bug_ids=[229367, 400095])
        assert bugids == {'229367': None}
