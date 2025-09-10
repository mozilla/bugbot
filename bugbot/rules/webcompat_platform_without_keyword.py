# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime
from typing import Any, Optional

import dateutil

from bugbot import gcp
from bugbot.bzcleaner import BzCleaner


class WebcompatPlatformWithoutKeyword(BzCleaner):
    normal_changes_max = 200

    def __init__(self):
        super().__init__()
        self.last_bugzilla_import_time: Optional[datetime] = None

    def description(self) -> str:
        return "Web Compat platform bugs without webcompat:platform-bug keyword"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

    def get_autofix_change(self):
        return {
            "keywords": {"add": ["webcompat:platform-bug"]},
        }

    def handle_bug(
        self, bug: dict[str, Any], data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        bug_id = str(bug["id"])

        # If the bug was updated later than our latest bugzilla data there could be a race,
        # so prefer to do nothing.
        if (
            self.last_bugzilla_import_time
            and dateutil.parser.parse(bug["last_change_time"])
            > self.last_bugzilla_import_time
        ):
            return None

        self.autofix_changes[bug_id] = self.get_autofix_change()
        return bug

    def get_bz_params(self, date) -> dict[str, Any]:
        fields = ["id", "summary", "keywords", "last_change_time"]
        return {"include_fields": fields, "id": self.get_bug_ids()}

    def get_bug_ids(self) -> list[int]:
        project = "moz-fx-dev-dschubert-wckb"
        dataset = "webcompat_knowledge_base"

        client = gcp.get_bigquery_client(project, ["cloud-platform", "drive"])

        last_run_at_rows = list(
            client.query(
                f"""
SELECT run_at FROM `{project}.{dataset}.import_runs` WHERE is_history_fetch_completed ORDER BY run_at DESC LIMIT 1
"""
            ).result()
        )
        if last_run_at_rows:
            self.last_bugzilla_import_time = last_run_at_rows[0]["run_at"]

        query = f"""
WITH webcompat_removed AS (
  SELECT number FROM `{project}.{dataset}.bugs_history` as bugs_history
  JOIN bugs_history.changes AS changes
  WHERE changes.field_name = "keywords" AND changes.removed = "webcompat:platform-bug"
),

site_reports AS (
  SELECT DISTINCT bugs.number AS number FROM `{project}.{dataset}.bugzilla_bugs` AS bugs
  JOIN `{project}.{dataset}.breakage_reports` as breakage_reports ON bugs.number = breakage_reports.breakage_bug
  JOIN `{project}.{dataset}.breakage_reports_core_bugs` as breakage_reports_core_bugs ON bugs.number = breakage_reports_core_bugs.breakage_bug
  LEFT JOIN webcompat_removed ON webcompat_removed.number = bugs.number
  JOIN `{project}.{dataset}.bugzilla_bugs` AS core_bugs ON breakage_reports_core_bugs.core_bug = core_bugs.number
  WHERE "webcompat:platform-bug" NOT IN UNNEST(bugs.keywords) AND "webcompat:needs-diagnosis" NOT IN UNNEST(bugs.keywords) AND bugs.resolution = "" AND core_bugs.resolution = "" AND webcompat_removed.number IS NULL
),

core_bugs AS (
  SELECT core_bug AS number
  FROM `{project}.{dataset}.prioritized_kb_entries` as kb_entries
  JOIN `{project}.{dataset}.bugzilla_bugs` as bugzilla_bugs ON bugzilla_bugs.number = kb_entries.core_bug
  WHERE "webcompat:platform-bug" not in UNNEST(bugzilla_bugs.keywords)
)

SELECT number FROM (
  SELECT number FROM site_reports
  UNION ALL
  SELECT number FROM core_bugs
)
LIMIT {self.normal_changes_max}
"""

        return list(row["number"] for row in client.query(query).result())


if __name__ == "__main__":
    WebcompatPlatformWithoutKeyword().run()
