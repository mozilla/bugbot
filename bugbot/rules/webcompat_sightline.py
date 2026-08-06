# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from bugbot import gcp
from bugbot.bzcleaner import Bug, BzCleaner


@dataclass(frozen=True)
class MetricType:
    field: str
    whiteboard_entry: str


metrics = [
    MetricType("is_sightline", "[webcompat:sightline]"),
    MetricType("is_japan_1000", "[webcompat:japan]"),
    MetricType("is_core", "[webcompat:core]"),
]


class WebcompatSightline(BzCleaner):
    def __init__(self):
        super().__init__()
        self.update_bugs = {}

    def description(self) -> str:
        return "Bugs with the [webcompat:<metric name>] or [webcompat-list:<name>] whiteboard tags updated"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

    def columns(self) -> list[str]:
        return ["id", "summary", "whiteboard"]

    def handle_bug(self, bug: Bug, data: dict[str, Any]) -> Optional[Bug]:
        bug_id = str(bug["id"])
        whiteboard = bug["whiteboard"]

        bug_metrics = self.update_bugs[bug["id"]]

        for whiteboard_entry, include in bug_metrics.items():
            if include and whiteboard_entry not in whiteboard:
                whiteboard += whiteboard_entry
            elif not include and whiteboard_entry in whiteboard:
                whiteboard = whiteboard.replace(whiteboard_entry, "")

        if whiteboard != bug["whiteboard"]:
            self.autofix_changes[bug_id] = {"whiteboard": whiteboard}
            data[bug_id] = {"whiteboard": whiteboard}
            return bug

        return None

    def get_bz_params(self, date) -> dict[str, Any]:
        fields = ["id", "summary", "whiteboard"]
        self.update_bugs = self.get_update_bugs()
        # Get all bugs that either have, or should have, one of the specified whiteboard entries
        return {
            "include_fields": fields,
            "j_top": "OR",
            "f1": "bug_id",
            "o1": "anyexact",
            "v1": ",".join(str(item) for item in self.update_bugs.keys()),
        }

    def get_update_bugs(self) -> Mapping[int, Mapping[str, bool]]:
        project = "moz-fx-dev-dschubert-wckb"
        dataset = "webcompat_knowledge_base"

        fields = []
        conditions = []
        results = {}

        client = gcp.get_bigquery_client(project, ["cloud-platform", "drive"])

        # Bugs that are part of a defined metric
        for metric in metrics:
            fields.append(metric.field)
            conditions.append(
                f"""({metric.field} != CONTAINS_SUBSTR(bugs.whiteboard, "{metric.whiteboard_entry}"))"""
            )

        query_metrics = f"""
        SELECT number, {", ".join(fields)} FROM `{project}.{dataset}.scored_site_reports` as bugs
        WHERE bugs.resolution = "" AND ({" OR ".join(conditions)})
        """

        for row in client.query(query_metrics).result():
            result = {metric.whiteboard_entry: row[metric.field] for metric in metrics}
            results[row.number] = result

        # Bugs that are part of some webcompat focus list
        query_webcompat_list = f"""
        WITH
        webcompat_lists AS (
          SELECT `{project}.{dataset}.WEBCOMPAT_HOST`(host) as host, CONCAT("[webcompat-list:", list_name, "]") AS whiteboard_entry
          FROM `{project}.{dataset}.webcompat_lists`
        ),

        bugs AS (
          SELECT number, webcompat_lists.whiteboard_entry, webcompat_lists.host, INSTR(bugs.whiteboard, whiteboard_entry) != 0 AS has_whiteboard_entry
          FROM `{project}.{dataset}.site_reports` as bugs
          LEFT JOIN webcompat_lists ON `{project}.{dataset}.WEBCOMPAT_HOST`(bugs.url) = webcompat_lists.host
          WHERE bugs.resolution = ""
        )

        SELECT DISTINCT number, whiteboard_entry
        FROM bugs
        WHERE NOT has_whiteboard_entry AND host is NOT NULL
        """

        for row in client.query(query_webcompat_list).result():
            if row.number not in results:
                results[row.number] = {}
            # In this case never remove a label since there could be non-URL criteria
            results[row.number][row.whiteboard_entry] = True

        return results


if __name__ == "__main__":
    WebcompatSightline().run()
