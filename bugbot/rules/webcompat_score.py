# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Any, Optional

from bugbot import gcp
from bugbot.bzcleaner import BzCleaner


class WebcompatScore(BzCleaner):
    def __init__(self):
        super().__init__()
        self.scored_bugs = {}

    def description(self) -> str:
        return "Update WebCompat score fields"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

    def handle_bug(
        self, bug: dict[str, Any], data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        scored_bugs_key = bug["id"]
        bug_id = str(bug["id"])

        if (
            scored_bugs_key in self.scored_bugs
            and bug["cf_webcompat_score"] != self.scored_bugs[scored_bugs_key]
        ):
            self.autofix_changes[bug_id] = {
                "cf_webcompat_score": self.scored_bugs[scored_bugs_key]
            }
            return bug

        return None

    def get_bz_params(self, date) -> dict[str, Any]:
        fields = ["id", "cf_webcompat_score"]
        self.scored_bugs = self.get_bug_scores()
        return {
            "include_fields": fields,
            "resolution": "---",
            "j_top": "OR",
            "f1": "OP",
            "f2": "product",
            "o2": "equals",
            "v2": "Web Compatibility",
            "f3": "component",
            "o3": "equals",
            "v3": "Site Reports",
            "f4": "CP",
            "f5": "OP",
            "f6": "product",
            "o6": "notequals",
            "v6": "Web Compatibility",
            "f7": "keywords",
            "o7": "equals",
            "v7": "webcompat:site-report",
            "f8": "CP",
        }

    def get_bug_scores(self) -> dict[int, str]:
        project = "moz-fx-dev-dschubert-wckb"
        dataset = "webcompat_knowledge_base"

        client = gcp.get_bigquery_client(project, ["cloud-platform", "drive"])
        query = f"""
        SELECT bugs.number, cast(buckets.score_bucket as string) as score_bucket FROM `{project}.{dataset}.site_reports_bugzilla_buckets` as buckets
        JOIN `{project}.{dataset}.bugzilla_bugs` as bugs ON bugs.number = buckets.number
        WHERE bugs.resolution = ""
        """

        return {
            row["number"]: row["score_bucket"] for row in client.query(query).result()
        }


if __name__ == "__main__":
    WebcompatScore().run()
