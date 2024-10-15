# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Any, Optional

from bugbot import gcp
from bugbot.bzcleaner import BzCleaner


class WebcompatSightline(BzCleaner):
    normal_changes_max = 1000
    whiteboard_entry = "[webcompat:sightline]"

    def __init__(self):
        super().__init__()
        self.autofix_changes = {}
        self.sightline_ids = []

    def description(self) -> str:
        return "Web Compat site report in the sightline metric set"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

    def get_autofix_change(self) -> dict[str, Any]:
        return self.autofix_changes

    def handle_bug(
        self, bug: dict[str, Any], data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        bug_id = str(bug["id"])
        whiteboard = bug["whiteboard"]

        if bug["id"] in self.sightline_ids:
            if self.whiteboard_entry not in whiteboard:
                self.autofix_changes[bug_id] = {
                    "whiteboard": whiteboard + self.whiteboard_entry
                }
        elif self.whiteboard_entry in whiteboard:
            self.autofix_changes[bug_id] = {
                "whiteboard": whiteboard.replace(self.whiteboard_entry, "")
            }

        return None

    def get_bz_params(self, date) -> dict[str, Any]:
        fields = ["id", "summary", "whiteboard"]
        self.sightline_ids = self.get_bug_ids()
        # Get all bugs that either have, or should have, the [webcompat:sightline]
        # whiteboard entry
        return {
            "include_fields": fields,
            "j_top": "OR",
            "f1": "bug_id",
            "o1": "anyexact",
            "v1": ",".join(str(item) for item in self.sightline_ids),
            "f2": "status_whiteboard",
            "o2": "substring",
            "v2": self.whiteboard_entry,
        }

    def get_bug_ids(self) -> list[int]:
        project = "moz-fx-dev-dschubert-wckb"
        dataset = "webcompat_knowledge_base"

        client = gcp.get_bq_client(project, ["cloud-platform", "drive"])
        query = f"""
        SELECT number FROM `{project}.{dataset}.webcompat_topline_metric_site_reports` as bugs
        """

        return list(row["number"] for row in client.query(query).result())


if __name__ == "__main__":
    WebcompatSightline().run()
