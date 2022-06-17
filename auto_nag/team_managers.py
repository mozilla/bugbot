# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
from collections import defaultdict
from typing import Dict, Optional

from libmozdata.bugzilla import BugzillaProduct, BugzillaUser

from auto_nag.people import People

DEFAULT_PATH = "./auto_nag/scripts/configs/team_managers.json"


class TeamManagers:
    def __init__(self):
        self.component_teams = {}
        self._load_team_managers(DEFAULT_PATH)

    def _load_team_managers(self, filepath: str):
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
    ) -> Optional[Dict[str, str]]:
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

    def _fetch_component_teams(self):
        include_fields = [
            "components.name",
            "components.team_name",
        ]

        def handler(product, data):
            data.update(
                {
                    component["name"]: component["team_name"]
                    for component in product["components"]
                }
            )

        # This is workaround until merging https://github.com/mozilla/libmozdata/pull/198
        search = "type=accessible&include_fields=" + ",".join(include_fields)
        BugzillaProduct(
            search_strings=search,
            product_handler=handler,
            product_data=self.component_teams,
        ).wait()

    def _fetch_managers_nicknames(self):
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
        self, component: str, fallback: bool = True
    ) -> Optional[dict]:
        """Get the manager of the team who owns the provided component.

        Args:
            component: the name of the component.
            fallback: if True, will return the fallback manager when cannot find
                the component manager; if False, will return None.

        Returns:
            Info for the manager of team who owns the component.
        """
        if not self.component_teams:
            self._fetch_component_teams()
            self._fetch_managers_nicknames()

        team_name = self.component_teams[component]
        return self.get_team_manager(team_name, fallback=fallback)
