# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import urllib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from bugbot import gcp
from bugbot.bzcleaner import BzCleaner


@dataclass
class FeatureUrls:
    feature: str
    spec_url: Optional[list[str]]
    feature_url: str
    sp_url: Optional[str]


def url_keys(urls: Iterable[str]) -> Mapping[tuple[str, str], str]:
    rv = {}
    for url in urls:
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.hostname is None:
                continue
            rv[(parsed.hostname, parsed.path)] = url
        except ValueError:
            pass
    return rv


class WebPlatformFeatures(BzCleaner):
    def __init__(self) -> None:
        super().__init__()
        self.feature_bugs: Mapping[int, FeatureUrls] = {}

    def description(self) -> str:
        return "Update See Also for web-features bugs"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

    def columns(self) -> list[str]:
        return ["id", "summary", "added"]

    def handle_bug(
        self, bug: dict[str, Any], data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        features_key = bug["id"]
        bug_id = str(bug["id"])

        changes = {}
        if bug_id not in data:
            data[bug_id] = {}
        data[bug_id]["added"] = []
        if features_key in self.feature_bugs:
            see_also_keys = url_keys(bug["see_also"])

            feature_urls = self.feature_bugs[features_key]
            expected_urls = [feature_urls.feature_url]
            if feature_urls.sp_url is not None:
                expected_urls.append(feature_urls.sp_url)
            if feature_urls.spec_url is not None:
                expected_urls.extend(feature_urls.spec_url)
            expected_keys = url_keys(expected_urls)
            add_urls = [
                url for key, url in expected_keys.items() if key not in see_also_keys
            ]
            if add_urls:
                changes["see_also"] = bug["see_also"] + add_urls
                data[bug_id]["added"] = add_urls

        if changes:
            self.autofix_changes[bug_id] = changes
            return bug

        return None

    def get_bz_params(self, date) -> dict[str, str | int | list[str] | list[int]]:
        fields = ["id", "see_also"]
        self.feature_bugs = self.get_feature_bugs()
        print(self.feature_bugs)
        return {"include_fields": fields, "id": list(self.feature_bugs.keys())}

    def get_feature_bugs(self) -> Mapping[int, FeatureUrls]:
        project = "moz-fx-dev-dschubert-wckb"

        client = gcp.get_bigquery_client(project, ["cloud-platform", "drive"])
        query = f"""
WITH feature_bugs as (
  SELECT
    bugs.number,
    feature,
    bugs.see_also,
    web_features.spec as spec_url,
    concat("https://web-platform-dx.github.io/web-features-explorer/features/", feature, "/") as feature_url,
    concat("https://github.com/mozilla/standards-positions/issues/", sp_mozilla.issue) as sp_url
  FROM `{project}.webcompat_knowledge_base.bugzilla_bugs` AS bugs
  JOIN `{project}.web_features.features_latest` AS web_features
    ON web_features.feature IN UNNEST(`{project}.webcompat_knowledge_base.EXTRACT_ARRAY`(bugs.user_story, "$.web-feature"))
  LEFT JOIN `{project}.standards_positions.mozilla_standards_positions` AS sp_mozilla
    ON `{project}.webcompat_knowledge_base.BUG_ID_FROM_BUGZILLA_URL`(sp_mozilla.bug) = bugs.number
)

SELECT number, feature, spec_url, feature_url, sp_url FROM feature_bugs
WHERE
  NOT EXISTS(SELECT 1 FROM feature_bugs.spec_url WHERE spec_url NOT IN UNNEST(see_also))
  OR feature_url NOT IN UNNEST(see_also)
  OR sp_url NOT IN UNNEST(see_also)
"""

        return {
            row["number"]: FeatureUrls(
                feature=row["feature"],
                spec_url=row["spec_url"],
                feature_url=row["feature_url"],
                sp_url=row["sp_url"],
            )
            for row in client.query(query).result()
        }


if __name__ == "__main__":
    WebPlatformFeatures().run()
