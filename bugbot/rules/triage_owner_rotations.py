# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from typing import List, Set
from urllib.parse import quote_plus

from libmozdata.bugzilla import BugzillaComponent
from requests import HTTPError
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_message,
    stop_after_attempt,
    wait_exponential,
)

from bugbot import logger
from bugbot.bzcleaner import BzCleaner
from bugbot.component_triagers import ComponentName, ComponentTriagers, TriageOwner


class TriageOwnerRotations(BzCleaner):
    def __init__(
        self,
        excluded_teams: List[str] = [
            "Layout",
            "GFX",
        ],
    ) -> None:
        """Constructor

        Args:
            excluded_teams: teams to excluded all of their components when
                performing the triage owner rotation.
        """
        super().__init__()
        self.component_triagers = ComponentTriagers(excluded_teams=excluded_teams)
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
            logger.info(
                "The triage owner for '%s' will be: '%s'",
                new_triager.component,
                new_triager.bugzilla_email,
            )

            if not self.dryrun and not self.test_mode:
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

    def get_email_data(self, date: str) -> List[dict]:
        new_triagers = self.component_triagers.get_new_triage_owners()
        failures = self._update_triage_owners(new_triagers)
        self.has_put_errors = len(failures) > 0

        email_data = []

        for new_triager in new_triagers:
            data = {
                "component": new_triager.component,
                "old_triage_owner": self.component_triagers.get_current_triage_owner(
                    new_triager.component
                ),
                "new_triage_owner": new_triager.bugzilla_email,
                "has_put_error": new_triager.component in failures,
                "link_to_triage": self.convert_to_url(str(new_triager.component)),
            }

            data["cc_emails"] = [data["old_triage_owner"], data["new_triage_owner"]]

            email_data.append(data)

        return email_data

    def convert_to_url(self, component: str) -> str:
        # replace double colons with a single colon
        component = component.replace("::", ":")

        encoded = quote_plus(component)

        url = "https://bugdash.moz.tools/?component=" + encoded

        return url


if __name__ == "__main__":
    TriageOwnerRotations().run()
