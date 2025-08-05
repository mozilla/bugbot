# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Any, Mapping, Optional

from bugbot import gcp
from bugbot.bzcleaner import BzCleaner


class WebcompatSightline(BzCleaner):
    WHITEBOARD_ENTRY = "[webcompat:sightline]"

    def __init__(self):
        super().__init__()
        self.sightline_data = {}

    def description(self) -> str:
        return "Bugs with the [webcompat:sightline] whiteboard tag updated"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

    def handle_bug(
        self, bug: dict[str, Any], data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        bug_id = str(bug["id"])
        whiteboard = bug["whiteboard"]

        if bug["id"] not in self.sightline_data:
            return None

        is_sightline = self.sightline_data[bug["id"]]
        has_whiteboard = self.WHITEBOARD_ENTRY in whiteboard
        if is_sightline and not has_whiteboard:
            self.autofix_changes[bug_id] = {
                "whiteboard": whiteboard + self.WHITEBOARD_ENTRY
            }
            return bug
        if not is_sightline and has_whiteboard:
            self.autofix_changes[bug_id] = {
                "whiteboard": whiteboard.replace(self.WHITEBOARD_ENTRY, "")
            }
            return bug

        return None

    def get_bz_params(self, date) -> dict[str, Any]:
        fields = ["id", "summary", "whiteboard"]
        self.sightline_data = self.get_sightline_bug_data()
        return {"include_fields": fields, "id": list(self.sightline_data.keys())}
        return fields

    def get_sightline_bug_data(self) -> Mapping[int, bool]:
        project = "moz-fx-dev-dschubert-wckb"
        dataset = "webcompat_knowledge_base"

        client = gcp.get_bigquery_client(project, ["cloud-platform", "drive"])
        query = f"""
        SELECT number, bugs.is_sightline FROM `{project}.{dataset}.scored_site_reports` as bugs
        WHERE (bugs.is_sightline AND NOT CONTAINS_SUBSTR(bugs.whiteboard, "{self.WHITEBOARD_ENTRY}"))
          OR (NOT bugs.is_sightline AND CONTAINS_SUBSTR(bugs.whiteboard, "{self.WHITEBOARD_ENTRY}"))
        """

        return {
            row["number"]: row["is_sightline"] for row in client.query(query).result()
        }


if __name__ == "__main__":
    WebcompatSightline().run()
