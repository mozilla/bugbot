# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Dict, List, NamedTuple

from libmozdata.bugzilla import BugzillaProduct


class ComponentName(NamedTuple):
    """A representation of a component name"""

    product: str
    name: str

    def __str__(self) -> str:
        return f"{self.product}::{self.name}"

    @classmethod
    def from_str(cls, pc: str) -> "ComponentName":
        """Parse the staring repression of the component name"""
        splitted_name = pc.split("::", 1)
        assert (
            len(splitted_name) == 2
        ), f"The component name should be formatted as `product::component`; got '{pc}'"

        return cls(*splitted_name)

    @classmethod
    def from_bug(cls, bug: dict) -> "ComponentName":
        """Extract the component name from a bug"""
        return cls(bug["product"], bug["component"])


class Components:
    """Bugzilla components"""

    _instance = None

    def __init__(self) -> None:
        self.team_components: Dict[str, list] = {}
        self._fetch_components()

    def _fetch_components(
        self,
    ) -> None:
        def handler(product, data):
            if not product["is_active"]:
                return

            for component in product["components"]:
                if not component["is_active"]:
                    continue

                team_name = component["team_name"]
                component_name = ComponentName(product["name"], component["name"])
                if team_name not in data:
                    data[team_name] = [component_name]
                else:
                    data[team_name].append(component_name)

        BugzillaProduct(
            product_types="accessible",
            include_fields=[
                "name",
                "is_active",
                "components.name",
                "components.team_name",
                "components.is_active",
            ],
            product_handler=handler,
            product_data=self.team_components,
        ).wait()

    @staticmethod
    def get_instance() -> "Components":
        """Get an instance of the Components class; if the method has been
        called before, a cached instance will be returned.
        """
        if Components._instance is None:
            Components._instance = Components()

        return Components._instance

    def get_team_components(self, team_name: str) -> List[ComponentName]:
        """Get all components owned by a team.

        Args:
            team_name: the name of the team.

         Returns:
            A list of all active components owned by the team.
        """
        return self.team_components[team_name]


def fetch_component_teams() -> Dict[ComponentName, str]:
    """Fetch all accessible components and their teams.

    Returns:
        A dictionary mapping a component name to its team name.
    """
    component_teams: Dict[ComponentName, str] = {}

    def handler(product, data):
        data.update(
            {
                ComponentName(product["name"], component["name"]): component[
                    "team_name"
                ]
                for component in product["components"]
            }
        )

    BugzillaProduct(
        product_types="accessible",
        include_fields=["name", "components.name", "components.team_name"],
        product_handler=handler,
        product_data=component_teams,
    ).wait()

    return component_teams
