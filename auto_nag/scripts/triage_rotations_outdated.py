# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import csv
from typing import List

from auto_nag.bzcleaner import BzCleaner
from auto_nag.component_triagers import ComponentName
from auto_nag.components import Components
from auto_nag.people import People
from auto_nag.round_robin import RotationDefinitions


class TriageRotationsOutdated(BzCleaner):
    """Find outdated triage owner rotation definitions"""

    def __init__(self) -> None:
        super().__init__()
        self.query_url = None

    def description(self) -> str:
        return "Outdated triage rotation definitions"

    def get_email_data(self, date: str, bug_ids: List[int]) -> List[dict]:
        active_components = {
            component: team_name
            for team_name, team_components in Components.get_instance().team_components.items()
            for component in team_components
        }
        people = People.get_instance()

        data = []
        for row in csv.DictReader(RotationDefinitions().get_definitions_csv_lines()):
            team_name = row["Team Name"]
            scope = row["Calendar Scope"]
            fallback_triager = row["Fallback Triager"]

            problems = []

            if not people.get_bzmail_from_name(fallback_triager):
                problems.append(
                    "The fallback person is not in the list of current employees."
                )

            if "::" in scope:
                component_name = ComponentName.from_str(scope)
                team_name_on_bugzilla = active_components.get(component_name)

                if not team_name_on_bugzilla:
                    problems.append(
                        "The component is not in the list of active components."
                    )

                elif team_name_on_bugzilla != team_name:
                    problems.append(
                        f"The team name on Bugzilla is '{team_name_on_bugzilla}'."
                    )
            elif scope != "All Team's Components":
                # This should never happen, but just in case.
                problems.append("Unexpected calendar scope.")

            if problems:
                data.append(
                    {
                        "team_name": team_name,
                        "scope": scope,
                        "fallback_triager": fallback_triager,
                        "problems": problems,
                    }
                )

        return data


if __name__ == "__main__":
    TriageRotationsOutdated().run()
