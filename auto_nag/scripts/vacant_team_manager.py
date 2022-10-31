# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from typing import List

from libmozdata.bugzilla import BugzillaProduct

from auto_nag.bzcleaner import BzCleaner
from auto_nag.team_managers import TeamManagers


class TeamManagerVacant(BzCleaner):
    def __init__(self) -> None:
        super(TeamManagerVacant, self).__init__()
        self.query_url = None

    def description(self) -> str:
        return "Teams with managers that need to be assigned"

    def fetch_teams(self) -> List[dict]:
        data = []
        include_fields = [
            "is_active",
            "components.team_name",
            "components.is_active",
        ]

        def product_handler(product: dict):
            data.append(product)

        BugzillaProduct(
            product_names=self.get_products(),
            include_fields=include_fields,
            product_handler=product_handler,
        ).wait()

        return data

    def identify_vacant_teams(self) -> List[dict]:
        # We need team names for active components only.
        teams = {
            component["team_name"]
            for product in self.fetch_teams()
            if product["is_active"]
            for component in product["components"]
            if component["is_active"]
        }
        # Remove catch-all teams
        teams -= {"Mozilla", "Other"}
        # Add "fallback" so we make sure the "fallback" is active.
        teams.add("fallback")

        team_managers = TeamManagers()
        vacant_teams = []
        for team in teams:
            manager = team_managers.get_team_manager(team, fallback=False)

            if manager is not None and manager["mozilla_email"] is not None:
                continue

            if manager is not None:
                name = manager["name"]
            else:
                name = "Nobody"

            info = {
                "manager": name,
                "team": team,
                "status": "No longer in people" if manager is not None else "Undefined",
            }

            vacant_teams.append(info)

        return vacant_teams

    def get_email_data(self, date: str) -> List[dict]:
        return self.identify_vacant_teams()


if __name__ == "__main__":
    TeamManagerVacant().run()
