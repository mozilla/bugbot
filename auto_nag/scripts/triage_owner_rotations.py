# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from typing import List

from libmozdata.bugzilla import BugzillaComponent

from auto_nag import logger
from auto_nag.bzcleaner import BzCleaner
from auto_nag.component_triagers import ComponentTriagers, TriageOwner


class TriageOwnerRotations(BzCleaner):
    def __init__(self) -> None:
        super().__init__()
        self.query_url = None

    def description(self) -> str:
        return "Triage owners that got updated"

    def update_triage_owners(self, new_triage_owners: List[TriageOwner]) -> None:
        for new_triager in new_triage_owners:
            change = {"triage_owner": new_triager.bugzilla_email}
            if self.dryrun or self.test_mode:
                logger.info(
                    "The component %s::%s will be updated with:\n%s",
                    new_triager.product,
                    new_triager.component,
                    change,
                )
            else:
                BugzillaComponent(
                    new_triager.product,
                    new_triager.component,
                ).put(change)

    def get_email_data(self, date: str, bug_ids: List[int]) -> List[tuple]:
        component_triagers = ComponentTriagers()
        new_triagers = component_triagers.get_new_triage_owners()
        self.update_triage_owners(new_triagers)

        return [
            (
                new_triager.product,
                new_triager.component,
                component_triagers.get_current_triage_owner(
                    new_triager.product, new_triager.component
                ),
                new_triager.bugzilla_email,
            )
            for new_triager in new_triagers
        ]


if __name__ == "__main__":
    TriageOwnerRotations().run()
