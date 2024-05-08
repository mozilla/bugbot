# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from typing import List, Set

from jinja2 import Environment, FileSystemLoader
from libmozdata.bugzilla import BugzillaComponent
from requests import HTTPError
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_message,
    stop_after_attempt,
    wait_exponential,
)

from bugbot import logger, mail
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
            old_owner = self.component_triagers.get_current_triage_owner(
                new_triager.component
            )

            email_data.append(
                {
                    "component": new_triager.component,
                    "old_triage_owner": old_owner,
                    "new_triage_owner": new_triager.bugzilla_email,
                    "has_put_error": new_triager.component in failures,
                }
            )

            self.send_email_to_triage_owners(
                old_owner,
                new_triager.bugzilla_email,
                new_triager.component,
                "https://www.mozilla.org",
            )

        return email_data

    def send_email_to_triage_owners(self, old_email, new_email, component, details_url):
        """Send an email to the old and new triage owners about the switch."""
        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template("triage_owner_rotations_2.html")

        # Render the email body using the template and passing required details
        body = template.render(
            preamble="Triage Owner Update Notification",
            data=[
                {
                    "component": component,
                    "old_triage_owner": old_email,
                    "new_triage_owner": new_email,
                    "details_url": details_url,  # This is the new line to include the details URL
                    "has_put_error": False,  # Assuming no error by default, update as needed
                }
            ],
            table_attrs="",  # You need to define what HTML attributes you want for the table if any
        )

        subject = "Triage Owner Update"

        # Assuming mail.send is configured correctly in your environment
        mail.send(
            From="your-email@mozilla.com",
            To=[old_email, new_email],
            Subject=subject,
            Body=body,
            html=True,  # Assuming the email should be sent as HTML
            dryrun=True,  # Set to False to actually send emails
        )


if __name__ == "__main__":
    TriageOwnerRotations().run()
