# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Dict, List, NamedTuple

from libmozdata.bugzilla import BugzillaProduct


class ComponentName(NamedTuple):
    product: str
    name: str

    def __str__(self) -> str:
        return f"{self.product}::{self.name}"

    @classmethod
    def from_str(cls, pc: str) -> "ComponentName":
        splitted_name = pc.split("::", 1)
        assert (
            len(splitted_name) == 2
        ), f"The component name should be formatted as `product::component`; got '{pc}'"

        return cls(*splitted_name)


class Components:
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
        if Components._instance is None:
            Components._instance = Components()

        return Components._instance

    def get_team_components(self, team: str) -> List[ComponentName]:
        return self.team_components[team]
