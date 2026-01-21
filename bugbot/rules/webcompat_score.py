# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
from typing import Any, Iterator, Optional, cast

from bugbot import gcp
from bugbot.bzcleaner import BzCleaner


@dataclass
class Score:
    bucket: Optional[str]
    score: str
    webcompat_priority: Optional[str]


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

    def parse_user_story(self, user_story: str) -> Iterator[tuple[str, str]]:
        """Parse the user story assuming it's lines of the form key: value.

        If there isn't a colon in the line we simply set value to the full line."""

        for line in user_story.splitlines():
            parts = line.split(":", 1)
            if len(parts) == 1:
                yield "", parts[0]
            yield cast(tuple[str, str], tuple(parts))

    def updated_user_story(self, user_story: str, score: str) -> Optional[str]:
        new_user_story = []
        has_user_impact_score = False
        updated_user_impact_score = False

        for key, value in self.parse_user_story(user_story):
            if not key:
                new_user_story.append(value)
                continue

            if key.strip() == "user-impact-score":
                if has_user_impact_score:
                    continue
                has_user_impact_score = True
                if value.strip() != score:
                    value = score
                    updated_user_impact_score = True
            new_user_story.append(f"{key}:{value}")

        if not has_user_impact_score:
            new_user_story.append(f"user-impact-score:{score}")
            updated_user_impact_score = True

        if updated_user_impact_score:
            return "\n".join(new_user_story)

        return None

    def handle_bug(
        self, bug: dict[str, Any], data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        scored_bugs_key = bug["id"]
        bug_id = str(bug["id"])

        changes = {}
        if scored_bugs_key in self.scored_bugs:
            bug_score = self.scored_bugs[scored_bugs_key]

            for key, new_value in [
                ("cf_webcompat_priority", bug_score.webcompat_priority),
                ("cf_webcompat_score", bug_score.bucket),
            ]:
                if new_value is not None and bug[key] != new_value:
                    changes[key] = new_value

            updated_user_story = self.updated_user_story(
                bug["cf_user_story"], bug_score.score
            )

            if updated_user_story:
                changes["cf_user_story"] = updated_user_story

        if changes:
            self.autofix_changes[bug_id] = changes
            return bug

        return None

    def get_bz_params(self, date) -> dict[str, Any]:
        fields = ["id", "cf_webcompat_score", "cf_user_story", "cf_webcompat_priority"]
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
            "f9": "OP",
            "f10": "product",
            "o10": "notequals",
            "v10": "Web Compatibility",
            "f11": "keywords",
            "o11": "equals",
            "v11": "webcompat:platform-bug",
            "f12": "CP",
        }

    def get_bug_scores(self) -> dict[int, Score]:
        project = "moz-fx-dev-dschubert-wckb"
        dataset = "webcompat_knowledge_base"

        client = gcp.get_bigquery_client(project, ["cloud-platform", "drive"])
        query = f"""
        SELECT number,
               cast(buckets.score as string) as score,
               cast(buckets.score_bucket as string) as bucket,
               CONCAT("P", CAST(buckets.webcompat_priority AS STRING)) AS webcompat_priority
        FROM `{project}.{dataset}.site_reports_bugzilla_buckets` as buckets
        JOIN `{project}.{dataset}.bugzilla_bugs` as bugs USING(number)
        WHERE bugs.resolution = ""
        UNION ALL
        SELECT number,
               cast(score_all as string) as score,
               NULL as bucket,
               NULL as webcompat_priority
        FROM `{project}.{dataset}.core_bugs_scores`
        WHERE resolution = ""
        """

        return {
            row["number"]: Score(
                score=row["score"],
                bucket=row["bucket"],
                webcompat_priority=row["webcompat_priority"],
            )
            for row in client.query(query).result()
        }


if __name__ == "__main__":
    WebcompatScore().run()
