# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
from typing import Dict, List, Set

from libmozdata.bugzilla import BugzillaProduct

from bugbot.components import ComponentName
from bugbot.round_robin import RoundRobin


@dataclass
class TriageOwner:
    component: ComponentName
    bugzilla_email: str


class ComponentTriagers:
    def __init__(
        self,
        excluded_teams: List[str] = [],
    ) -> None:
        """Constructor

        Args:
            excluded_teams: teams to excluded all of their components.
        """
        self.round_robin: RoundRobin = RoundRobin.get_instance()
        self.triagers: Dict[ComponentName, str] = {}
        products = [
            ComponentName.from_str(pc).product
            for pc in self.round_robin.get_components()
        ]
        self._fetch_triagers(
            products,
            set(excluded_teams),
        )

    def _fetch_triagers(
        self,
        products: List[str],
        excluded_teams: Set[str],
    ) -> None:
        def handler(product, data):
            for component in product["components"]:
                component_name = ComponentName(product["name"], component["name"])
                if component["team_name"] not in excluded_teams:
                    data[component_name] = component["triage_owner"]

        BugzillaProduct(
            product_names=products,
            include_fields=[
                "name",
                "components.name",
                "components.team_name",
                "components.triage_owner",
            ],
            product_handler=handler,
            product_data=self.triagers,
        ).wait()

    def get_current_triage_owner(self, component: ComponentName) -> str:
        """Get the current triage owner as defined on Bugzilla.

        Args:
            component: the name of the component.

        Returns:
            The bugzilla email of the triage owner.
        """

        return self.triagers[component]

    def get_new_triage_owners(self) -> List[TriageOwner]:
        """Get the triage owners that are different than what are defined on
        Bugzilla.

        Returns:
            The new triage owner based on the rotation source (i.e., calendar).
            If the rotation source returns more than one person, the first one
            will be selected as the new triage owner.
        """
        triagers = []
        for component, current_triager in self.triagers.items():
            new_triager = self.round_robin.get(
                {
                    "product": component.product,
                    "component": component.name,
                    "triage_owner": current_triager,
                },
                "today",
                only_one=True,
                has_nick=False,
            )
            if new_triager and new_triager != current_triager:
                triagers.append(TriageOwner(component, new_triager))

        return triagers
