# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from typing import List, Set

from libmozdata.bugzilla import BugzillaComponent
from requests import HTTPError
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_message,
    stop_after_attempt,
    wait_exponential,
)

from auto_nag import logger
from auto_nag.bzcleaner import BzCleaner
from auto_nag.component_triagers import ComponentName, ComponentTriagers, TriageOwner


class TriageOwnerRotations(BzCleaner):
    def __init__(self) -> None:
        super().__init__()
        self.query_url = None
        self.has_put_errors = False

    def description(self) -> str:
        return "Triage owners that got updated"

    def get_extra_for_template(self):
        return {"has_put_errors": self.has_put_errors}

    def _update_triage_owners(
        self, new_triage_owners: List[TriageOwner]
    ) -> Set[ComponentName]:
        failures = set()
        for new_triager in new_triage_owners:
            if self.dryrun or self.test_mode:
                logger.info(
                    "The triage owner for '%s' will be: '%s'",
                    new_triager.component,
                    new_triager.bugzilla_email,
                )
            else:
                try:
                    self._put_new_triage_owner(new_triager)
                except (HTTPError, RetryError) as err:
                    failures.add(new_triager.component)
                    logger.exception(
                        "Cannot update the triage owner for '%s' to be '%s': %s",
                        new_triager.component,
                        new_triager.bugzilla_email,
                        err,
                    )

        return failures

    @retry(
        retry=retry_if_exception_message(match=r"^\d{3} Server Error"),
        wait=wait_exponential(),
        stop=stop_after_attempt(3),
    )
    def _put_new_triage_owner(self, new_triager: TriageOwner) -> None:
        change = {"triage_owner": new_triager.bugzilla_email}
        BugzillaComponent(
            new_triager.component.product,
            new_triager.component.name,
        ).put(change)

    def get_email_data(self, date: str, bug_ids: List[int]) -> List[dict]:
        component_triagers = ComponentTriagers()
        new_triagers = component_triagers.get_new_triage_owners()
        failures = self._update_triage_owners(new_triagers)
        self.has_put_errors = len(failures) > 0

        return [
            {
                "component": new_triager.component,
                "old_triage_owner": component_triagers.get_current_triage_owner(
                    new_triager.component
                ),
                "new_triage_owner": new_triager.bugzilla_email,
                "has_put_error": new_triager.component in failures,
            }
            for new_triager in new_triagers
        ]


if __name__ == "__main__":
    TriageOwnerRotations().run()
