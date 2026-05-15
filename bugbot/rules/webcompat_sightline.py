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
        return "Bugs with the [webcompat:<metric name>] whiteboard tag updated"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

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
            return bug

        return None

    def get_bz_params(self, date) -> dict[str, Any]:
        fields = ["id", "summary", "whiteboard"]
        self.update_bugs = self.get_update_bugs()
        # Get all bugs that either have, or should have, the [webcompat:sightline]
        # whiteboard entry
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

        for metric in metrics:
            fields.append(metric.field)
            conditions.append(
                f"""({metric.field} != CONTAINS_SUBSTR(bugs.whiteboard, "{metric.whiteboard_entry}"))"""
            )

        client = gcp.get_bigquery_client(project, ["cloud-platform", "drive"])
        query_metrics = f"""
        SELECT number, {", ".join(fields)} FROM `{project}.{dataset}.scored_site_reports` as bugs
        WHERE bugs.resolution = "" AND ({" OR ".join(conditions)})
        """

        for row in client.query(query_metrics).result():
            result = {metric.whiteboard_entry: row[metric.field] for metric in metrics}
            results[row.number] = result

        query_wc = f"""
        SELECT DISTINCT number, wc_urls.url IS NOT NULL AS is_wc_2026 FROM `{project}.{dataset}.site_reports` as bugs
        LEFT JOIN `{project}.{dataset}.world_cup_2026_urls` AS wc_urls ON `moz-fx-dev-dschubert-wckb.webcompat_knowledge_base.WEBCOMPAT_HOST`(bugs.url) = `moz-fx-dev-dschubert-wckb.webcompat_knowledge_base.WEBCOMPAT_HOST`(wc_urls.url)
        WHERE bugs.resolution = "" AND (wc_urls.url IS NOT NULL) != CONTAINS_SUBSTR(bugs.whiteboard, "[webcompat:wc2026]")
        """

        for row in client.query(query_wc).result():
            if row.number not in results:
                results[row.number] = {}
            results[row.number]["[webcompat:wc2026]"] = row["is_wc_2026"]

        return results


if __name__ == "__main__":
    WebcompatSightline().run()
