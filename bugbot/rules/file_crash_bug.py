# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pprint

import jinja2
import requests

from bugbot import logger
from bugbot.bzcleaner import BzCleaner
from bugbot.crash import socorro_util
from bugbot.crash.analyzer import DevBugzilla, SignatureAnalyzer, SignaturesDataFetcher
from bugbot.user_activity import UserActivity, UserStatus


class FileCrashBug(BzCleaner):
    """File bugs for new actionable crashes."""

    # NOTE: If you make changes that affect the output of the rule, you should
    # increment this number. This is needed in the experimental phase only.
    VERSION = 1
    MAX_BUG_TITLE_LENGTH = 255
    FILE_ON_BUGZILLA_DEV = True

    def __init__(self):
        super().__init__()

        self.bug_description_template = jinja2.Environment(
            loader=jinja2.FileSystemLoader("templates")
        ).get_template("file_crash_bug_description.md.jinja")

    def description(self):
        return "New actionable crashes"

    def columns(self):
        return ["component", "id", "summary"]

    def get_bz_params(self, date):
        return {
            "resolution": ["---", "FIXED"],
            "keywords": ["feature", "regression"],
            "keywords_type": "allwords",
        }

    def _active_regression_authors(
        self, signatures: list[SignatureAnalyzer]
    ) -> set[str]:
        """Get Bugzilla usernames for users who are active and can be needinfo'd.

        Args:
            signatures: a list of signatures for which to check the status of
                their regression author.

        Returns:
            A set of user emails.
        """
        ni_skiplist = self.get_auto_ni_skiplist()
        users = UserActivity(include_fields=["requests"]).check_users(
            (
                signature.regressed_by_author["name"]
                for signature in signatures
                if signature.regressed_by_author
            ),
            keep_active=True,
            fetch_employee_info=True,
        )

        return {
            name
            for name, user in users.items()
            if name not in ni_skiplist
            and user["status"] == UserStatus.ACTIVE
            and not user["requests"]["needinfo"]["blocked"]
        }

    def get_bugs(self, date):
        self.query_url = None
        bugs = {}

        signatures = SignaturesDataFetcher.find_new_actionable_crashes(
            "Firefox", "nightly"
        ).analyze()

        active_regression_authors = self._active_regression_authors(signatures)

        for signature in signatures:
            logger.debug("Generating bug for signature: %s", signature.signature_term)

            title = (
                f"Startup crash in [@ {signature.signature_term}]"
                if signature.is_startup_related_crash
                else f"Crash in [@ {signature.signature_term}]"
            )
            if len(title) > self.MAX_BUG_TITLE_LENGTH:
                title = title[: self.MAX_BUG_TITLE_LENGTH - 3] + "..."

            # Whether we should needinfo the regression author.
            needinfo_regression_author = (
                signature.regressed_by
                and signature.regressed_by_author["email"] in active_regression_authors
            )

            report = signature.fetch_representative_processed_crash()
            description = self.bug_description_template.render(
                {
                    **socorro_util.generate_bug_description_data(report),
                    "signature": signature,
                    "needinfo_regression_author": needinfo_regression_author,
                }
            )

            # TODO: Provide the following information:
            # [X] Crash signature
            # [X] Top 10 frames of crashing thread
            # [X] Component
            # [X] The kind of crash
            # [ ] Regression window
            # [X] Inducing patch
            # [X] Reason
            # [X] Regressed by
            # [X] Platform
            # [ ] Firefox status flags
            # [ ] Severity
            # [ ] Time correlation
            # [X] User comments
            # [X] Crash address commonalities
            # [ ] Estimated future crash volume

            bug_data = {
                "blocks": "bugbot-auto-crash",
                "type": "defect",
                "keywords": ["crash"],
                "status_whiteboard": f"[bugbot-crash-v{self.VERSION}]",
                "summary": title,
                "product": signature.crash_component.product,
                "component": signature.crash_component.name,
                "op_sys": signature.bugzilla_op_sys,
                "rep_platform": signature.bugzilla_cpu_arch,
                "cf_crash_signature": f"[@ {signature.signature_term}]",
                "description": description,
                # NOTE(suhaib): the following CC is for testing purposes only
                # to allow us access and evaluate security bugs. It should be
                # removed at some point after we move to production.
                "cc": [
                    "smujahid@mozilla.com",
                    "mcastelluccio@mozilla.com",
                    "aryx.bugmail@gmx-topmail.de",
                ],
            }

            # NOTE: Filling the `flags` field on bugzilla-dev will cause an
            # error when the user does not exist.
            if needinfo_regression_author and not self.FILE_ON_BUGZILLA_DEV:
                bug_data["flags"] = [
                    {
                        "name": "needinfo",
                        "requestee": signature.regressed_by_author["name"],
                        "status": "?",
                        "new": "true",
                    }
                ]

            if signature.regressed_by:
                bug_data["keywords"].append("regression")

            # NOTE: Filling the `regressed_by` field on bugzilla-dev will cause
            # "bug does not exist" errors.
            if signature.regressed_by and not self.FILE_ON_BUGZILLA_DEV:
                bug_data["regressed_by"] = signature.regressed_by

            if signature.is_potential_security_crash:
                bug_data["groups"] = ["core-security"]

            if self.dryrun:
                logger.info("Dry-run bug:")
                pprint.pprint(bug_data)
                bug_id = str(len(bugs) + 1)
            else:
                # NOTE: When moving to production:
                #   - Use Bugzilla instead of DevBugzilla
                #   - Drop the DevBugzilla class
                #   - Update the bug URL `file_crash_bug.html`
                #   - Drop the bug link `file_crash_bug_description.md.jinja`
                #   - Fill the `regressed_by` and `flags` fields
                #   - Create the bug using `utils.create_bug`
                #   - Drop the FILE_ON_BUGZILLA_DEV attribute
                resp = requests.post(
                    url=DevBugzilla.API_URL,
                    json=bug_data,
                    headers=DevBugzilla([]).get_header(),
                    verify=True,
                    timeout=DevBugzilla.TIMEOUT,
                )
                try:
                    resp.raise_for_status()
                except requests.HTTPError:
                    logger.exception(
                        "Failed to create a bug for signature %s: %s",
                        signature.signature_term,
                        resp.text,
                    )
                    continue

                bug = resp.json()
                bug_id = str(bug["id"])
                # TODO: log the created bugs info somewhere (e.g., DB,
                # spreadsheet, or LabelStudio)

            bugs[bug_id] = {
                "id": bug_id,
                "summary": "..." if signature.is_potential_security_crash else title,
                "component": signature.crash_component,
            }

        logger.debug("Total of %d bugs have been filed", len(bugs))

        return bugs


if __name__ == "__main__":
    FileCrashBug().run()
