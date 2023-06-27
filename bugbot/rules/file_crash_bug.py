# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pprint

import jinja2
import requests

from bugbot import logger
from bugbot.bzcleaner import BzCleaner
from bugbot.crash import socorro_util
from bugbot.crash.analyzer import DevBugzilla, SignaturesDataFetcher


class FileCrashBug(BzCleaner):
    """File bugs for new actionable crashes."""

    # NOTE: If you make changes that affect the output of the rule, you should
    # increment this number. This is needed in the experimental phase only.
    VERSION = 1
    MAX_BUG_TITLE_LENGTH = 255

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

    def get_bugs(self, date):
        self.query_url = None
        bugs = {}

        signatures = SignaturesDataFetcher.find_new_actionable_crashes(
            "Firefox", "nightly"
        )

        for signature in signatures.analyze():
            logger.debug("Generating bug for signature: %s", signature.signature_term)

            title = (
                f"Startup crash in [@ {signature.signature_term}]"
                if signature.is_startup_related_crash
                else f"Crash in [@ {signature.signature_term}]"
            )
            if len(title) > self.MAX_BUG_TITLE_LENGTH:
                title = title[: self.MAX_BUG_TITLE_LENGTH - 3] + "..."

            # TODO: Handle cases where the regressor is a security bug. In such
            # cases, we may want to file the bug as security bug.

            flags = None
            if signature.regressed_by:
                # TODO: check user activity and if the ni? is open
                flags = [
                    {
                        "name": "needinfo",
                        "requestee": signature.regressed_by_author["name"],
                        "status": "?",
                        "new": "true",
                    }
                ]

            report = signature.fetch_representing_processed_crash()
            description = self.bug_description_template.render(
                {
                    **socorro_util.generate_bug_description_data(report),
                    "signature": signature,
                    "needinfo_regression_author": bool(flags),
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
            # [ ] Crash address commonalities
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
                # TODO: Uncomment the following lines when we move to file on
                # the production instance of Bugzilla. Filling `regressed_by` or
                # `flags` on bugzilla-dev will cause "bug does not exist" errors.
                # "regressed_by": signature.regressed_by,
                # "flags": flags,
            }

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
                #   - Create the bug using `utils.create_bug``
                resp = requests.post(
                    url=DevBugzilla.API_URL,
                    json=bug_data,
                    headers=DevBugzilla([]).get_header(),
                    verify=True,
                    timeout=DevBugzilla.TIMEOUT,
                )
                resp.raise_for_status()
                bug = resp.json()
                bug_id = str(bug["id"])
                # TODO: log the created bugs info somewhere (e.g., DB,
                # spreadsheet, or LabelStudio)

            bugs[bug_id] = {
                "id": bug_id,
                "summary": title,
                "component": signature.crash_component,
            }

        logger.debug("Total of %d bugs have been filed", len(bugs))

        return bugs


if __name__ == "__main__":
    FileCrashBug().run()
