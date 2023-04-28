# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
from collections import defaultdict
from typing import Dict, Optional

from libmozdata.bugzilla import BugzillaUser

from bugbot.components import ComponentName, fetch_component_teams
from bugbot.people import People

DEFAULT_PATH = "./configs/team_managers.json"


class TeamManagers:
    def __init__(self):
        self._component_teams: Dict[ComponentName, str] = {}
        self._load_team_managers(DEFAULT_PATH)

    def _load_team_managers(self, filepath: str) -> None:
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
        self, team_name: str, fallback: bool = True
    ) -> Optional[Dict[str, dict]]:
        """Get the manager of the provided team.

        Args:
            team_name: the name of the team.
            fallback: if True, will return the fallback manager when cannot find
                the team manager; if False, will return None.

        Returns:
            Info for the team manager.
        """

        if team_name not in self.managers:
            if fallback:
                return self.managers["fallback"]
            else:
                return None

        return self.managers[team_name]

    def _fetch_managers_nicknames(self) -> None:
        people = People.get_instance()

        bz_emails_map = defaultdict(list)
        for manager in self.managers.values():
            moz_mail = manager["mozilla_email"]
            if not moz_mail:
                continue

            info = people.get_info(moz_mail)
            bz_mail = info["bugzillaEmail"]
            if not bz_mail:
                bz_mail = moz_mail

            # Some manager could manage multiple teams, we need to update all of
            # them.
            bz_emails_map[bz_mail].append(manager)

        def handler(user, data):
            for manager in data[user["email"]]:
                manager["nick"] = user["nick"]
                manager["bz_email"] = user["email"]

        BugzillaUser(
            list(bz_emails_map.keys()),
            include_fields=["email", "nick"],
            user_handler=handler,
            user_data=bz_emails_map,
        ).wait()

    def get_component_manager(
        self, product: str, component: str, fallback: bool = True
    ) -> Optional[Dict[str, dict]]:
        """Get the manager of the team who owns the provided component.

        Args:
            product: the name of the product.
            component: the name of the component.
            fallback: if True, will return the fallback manager when cannot find
                the component manager; if False, will return None.

        Returns:
            Info for the manager of team who owns the component.
        """
        if not self._component_teams:
            self._component_teams = fetch_component_teams()
            self._fetch_managers_nicknames()

        team_name = self._component_teams[ComponentName(product, component)]
        return self.get_team_manager(team_name, fallback=fallback)
