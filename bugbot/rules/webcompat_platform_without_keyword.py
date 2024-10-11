# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import gcp
from bugbot.bzcleaner import BzCleaner


class WebcompatPlatformWithoutKeyword(BzCleaner):
    normal_changes_max = 200

    def description(self):
        return "Web Compat platform bugs without webcompat:platform-bug keyword"

    def filter_no_nag_keyword(self):
        return False

    def has_default_products(self):
        return False

    def get_autofix_change(self):
        return {
            "keywords": {"add": ["webcompat:platform-bug"]},
        }

    def get_bz_params(self, date):
        fields = ["id", "summary", "keywords"]
        return {"include_fields": fields, "id": self.get_core_bug_ids()}

    def get_core_bug_ids(self):
        project = "moz-fx-dev-dschubert-wckb"
        dataset = "webcompat_knowledge_base"

        client = gcp.get_bigquery_client(project, ["cloud-platform", "drive"])
        query = f"""
        SELECT core_bug
        FROM `{project}.{dataset}.prioritized_kb_entries` as kb_entries
            JOIN `moz-fx-dev-dschubert-wckb.webcompat_knowledge_base.bugzilla_bugs` as bugzilla_bugs ON bugzilla_bugs.number = kb_entries.core_bug
        WHERE "webcompat:platform-bug" not in UNNEST(bugzilla_bugs.keywords)
        LIMIT {self.normal_changes_max}
        """

        return list(row["core_bug"] for row in client.query(query).result())


if __name__ == "__main__":
    WebcompatPlatformWithoutKeyword().run()
