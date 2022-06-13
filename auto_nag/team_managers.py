# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
from typing import Dict, Optional

from auto_nag.people import People

DEFAULT_PATH = "./auto_nag/scripts/configs/team_managers.json"


class TeamManagers:
    def __init__(self):
        self._load_team_managers(DEFAULT_PATH)

    def _load_team_managers(self, filepath):
        people = People.get_instance()

        with open(filepath) as file:
            self.managers = {
                team: {
                    "name": manager,
                    "mozilla_email": people.get_mozmail_from_name(manager),
                }
                for team, manager in json.load(file).items()
            }

    def get_team_manager(
        self, team_name: str, no_fallback: bool = False
    ) -> Optional[Dict[str, str]]:
        if team_name not in self.managers:
            if not no_fallback:
                return self.managers["fallback"]
            else:
                return None

        return self.managers[team_name]
