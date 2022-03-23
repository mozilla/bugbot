# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from auto_nag.team_managers import TeamManagers


class TestTeamManagers(unittest.TestCase):
    def test_get_team_manager(self):
        team_managers = TeamManagers()
        team_name = "DOM Core"
        assert team_managers.get_team_manager(team_name)["name"] == "Hsin-Yi Tsai"

    def test_get_team_manager_fallback(self):
        team_managers = TeamManagers()
        team_name = "A Team That IS Not Exist"
        assert team_managers.get_team_manager(team_name)["name"] == "Andrew Overholt"
