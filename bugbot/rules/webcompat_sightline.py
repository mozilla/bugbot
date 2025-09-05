# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from bugbot import gcp
from bugbot.bzcleaner import BzCleaner


@dataclass(frozen=True)
class MetricType:
    field: str
    whiteboard_entry: str


metrics = [
    MetricType("is_sightline", "[webcompat:sightline]"),
    MetricType("is_japan_1000", "[webcompat:japan]"),
]


class WebcompatSightline(BzCleaner):
    def __init__(self):
        super().__init__()
        self.metric_bugs = {}

    def description(self) -> str:
        return "Bugs with the [webcompat:<metric name>] whiteboard tag updated"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

    def handle_bug(
        self, bug: dict[str, Any], data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        bug_id = str(bug["id"])
        whiteboard = bug["whiteboard"]

        bug_metrics = self.metric_bugs[bug["id"]]

        for metric, include in bug_metrics.items():
            if include and metric.whiteboard_entry not in whiteboard:
                whiteboard += metric.whiteboard_entry
            elif not include and metric.whiteboard_entry in whiteboard:
                whiteboard = whiteboard.replace(metric.whiteboard_entry, "")

        if whiteboard != bug["whiteboard"]:
            self.autofix_changes[bug_id] = {"whiteboard": whiteboard}
            return bug

        return None

    def get_bz_params(self, date) -> dict[str, Any]:
        fields = ["id", "summary", "whiteboard"]
        self.metric_bugs = self.get_metric_bugs()
        # Get all bugs that either have, or should have, the [webcompat:sightline]
        # whiteboard entry
        query = {
            "include_fields": fields,
            "j_top": "OR",
            "f1": "bug_id",
            "o1": "anyexact",
            "v1": ",".join(str(item) for item in self.metric_bugs.keys()),
        }

        return query

    def get_metric_bugs(self) -> Mapping[int, Mapping[MetricType, bool]]:
        project = "moz-fx-dev-dschubert-wckb"
        dataset = "webcompat_knowledge_base"

        fields = []
        conditions = []

        for metric in metrics:
            fields.append(metric.field)
            conditions.append(
                f"""({metric.field} != CONTAINS_SUBSTR(bugs.whiteboard, "{metric.whiteboard_entry}"))"""
            )

        client = gcp.get_bigquery_client(project, ["cloud-platform", "drive"])
        query = f"""
        SELECT number, {", ".join(fields)} FROM `{project}.{dataset}.scored_site_reports` as bugs
        WHERE bugs.resolution = "" AND ({" OR ".join(conditions)})
        """

        results = {}
        for row in client.query(query).result():
            result = {metric: row[metric.field] for metric in metrics}
            results[row.number] = result

        return results


if __name__ == "__main__":
    WebcompatSightline().run()
