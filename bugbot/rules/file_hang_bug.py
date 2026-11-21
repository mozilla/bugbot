# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pprint
from dataclasses import dataclass

import jinja2
import requests

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner


@dataclass
class HangStack:
    """Data for a single BHR hang stack to file a bug for.

    This is the expected input shape from the data parsing layer.
    """

    function_name: str
    """Top frame function name, used in the whiteboard tag and bug title."""

    stack_frames: list[str]
    """Full stack frame strings for the hang."""

    total_duration_ms: float
    """Total hang duration in milliseconds."""

    total_count: int
    """Total number of hang occurrences."""

    product: str = "Core"
    """Bugzilla product for the bug."""

    component: str = "Performance"
    """Bugzilla component for the bug."""


class FileHangBug(BzCleaner):
    """File bugs for top BHR (Background Hang Reporter) hang stacks."""

    MAX_BUG_TITLE_LENGTH = 255

    def __init__(self):
        super().__init__()

        self.bug_description_template = jinja2.Environment(
            loader=jinja2.FileSystemLoader("templates")
        ).get_template("file_hang_bug_description.md.jinja")

    def description(self):
        return "New BHR hang bugs"

    def columns(self):
        return ["component", "id", "summary"]

    def get_bz_params(self, date):
        return {}

    def _fetch_hang_stacks(self) -> list[HangStack]:
        """Fetch and filter hang stacks that need bugs filed.

        TODO: Implement data fetching from the BHR hang-stats dashboard
        (https://fqueze.github.io/hang-stats/) and filtering logic to determine
        which stacks should have bugs filed.

        Returns:
            A list of HangStack objects for which bugs should be filed.
        """
        return []

    def get_bugs(self, date):
        self.query_url = None
        bugs = {}

        hang_stacks = self._fetch_hang_stacks()

        for hang in hang_stacks:
            logger.debug("Generating bug for hang stack: %s", hang.function_name)

            title = f"Main thread hang in {hang.function_name}"
            if len(title) > self.MAX_BUG_TITLE_LENGTH:
                title = title[: self.MAX_BUG_TITLE_LENGTH - 3] + "..."

            description = self.bug_description_template.render(
                {
                    "hang": hang,
                }
            )

            bug_data = {
                "blocks": ["bugbot-auto-hang"],
                "type": "defect",
                "keywords": ["perf:responsiveness"],
                "summary": title,
                "product": hang.product,
                "component": hang.component,
                "whiteboard": f"[bhr:{hang.function_name}]",
                "cf_performance_impact": "?",
                "description": description,
            }

            if self.dryrun:
                logger.info("Dry-run bug:")
                pprint.pprint(bug_data)
                bug_id = str(len(bugs) + 1)
            else:
                try:
                    bug = utils.create_bug(bug_data)
                except requests.HTTPError as err:
                    logger.exception(
                        "Failed to create a bug for hang stack %s: %s",
                        hang.function_name,
                        err.response.text,
                    )
                    continue

                bug_id = str(bug["id"])

            bugs[bug_id] = {
                "id": bug_id,
                "summary": title,
                "component": f"{hang.product}::{hang.component}",
            }

        logger.debug("Total of %d hang bugs have been filed", len(bugs))

        return bugs


if __name__ == "__main__":
    FileHangBug().run()
