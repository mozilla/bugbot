# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# mypy: disallow-untyped-defs
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import (
    Any,
    Generic,
    Iterable,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    TypeVar,
)
from urllib import parse

from google.cloud import bigquery

from bugbot import gcp
from bugbot.bzcleaner import Bug, BzCleaner

Json = None | str | int | float | Sequence["Json"] | Mapping[str, "Json"]


def parse_user_story(
    user_story: str,
) -> Iterator[tuple[str, Optional[str], Optional[str]]]:
    """Parse the user story assuming it's lines of the form key: value.

    If there isn't a colon in the line we simply set value to the full line."""
    user_story_re = re.compile(r"^\s*([^\s]+)\s*:\s*(.*)")
    for line in user_story.splitlines():
        key = None
        value = None
        m = user_story_re.match(line)
        if m is not None:
            maybe_key, maybe_value = m.groups()
            if maybe_value:
                key = maybe_key
                value = maybe_value
        yield line, key, value


class UserStoryChangeType(IntEnum):
    APPEND = 1
    REPLACE = 2
    DELETE = 3


@dataclass(frozen=True)
class UserStoryChange:
    field: str
    type: UserStoryChangeType
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class Resolution(Enum):
    NONE = ""
    FIXED = "FIXED"
    DUPLICATE = "DUPLICATE"


@dataclass
class AddRemoveChange:
    add: list[str] = field(default_factory=list)
    remove: list[str] = field(default_factory=list)

    def to_json(self) -> Optional[Json]:
        if self.add is None and self.remove is None:
            return None
        rv = {}
        if self.add:
            rv["add"] = self.add
        if self.remove:
            rv["remove"] = self.remove
        return rv

    def __bool__(self) -> bool:
        return bool(self.add or self.remove)


@dataclass
class BugzillaUpdate:
    """Representation of bug changes for use with the Bugzilla ReST API"""

    keywords: Optional[AddRemoveChange] = None
    see_also: Optional[AddRemoveChange] = None
    whiteboard: Optional[str] = None
    user_story: Optional[str] = None
    status: Optional[str] = None
    resolution: Optional[str] = None
    comment: Optional[str] = None

    def __bool__(self) -> bool:
        if any(add_remove_field for add_remove_field in [self.keywords, self.see_also]):
            return True
        return any(
            string_field is not None
            for string_field in [
                self.whiteboard,
                self.user_story,
                self.status,
                self.resolution,
                self.comment,
            ]
        )

    def to_json(self) -> Json:
        rv: dict[str, Json] = {}
        for add_remove_field, name in [
            (self.keywords, "keywords"),
            (self.see_also, "see_also"),
        ]:
            if add_remove_field is not None:
                value = add_remove_field.to_json()
                if value:
                    rv[name] = value

        for value, name in [
            (self.whiteboard, "whiteboard"),
            (self.status, "status"),
            (self.resolution, "resolution"),
            (self.user_story, "cf_user_story"),
        ]:
            if value is not None:
                rv[name] = value

        if self.comment is not None:
            rv["comment"] = {"body": self.comment}

        return rv


@dataclass
class FeatureBugUpdate:
    """Updates for a specific bug representing a web feature"""

    keywords: dict[str, bool] = field(default_factory=dict)
    see_also: dict[str, bool] = field(default_factory=dict)
    user_story: list[UserStoryChange] = field(default_factory=list)
    comment: list[str] = field(default_factory=list)
    comment_when_unchanged: bool = False
    resolve: Optional[Resolution] = None

    def update_keywords(self, current_keywords: set[str]) -> AddRemoveChange:
        return AddRemoveChange(
            add=[
                keyword
                for keyword, add_keyword in self.keywords.items()
                if add_keyword and keyword not in current_keywords
            ],
            remove=[
                keyword
                for keyword, add_keyword in self.keywords.items()
                if not add_keyword and keyword in current_keywords
            ],
        )

    def update_see_also(
        self, current_url: str, current_see_also: list[str]
    ) -> AddRemoveChange:
        add = []
        remove = []
        has_links = set([current_url] + current_see_also)
        has_link_keys = url_keys(has_links)
        expected_link_keys = url_keys(self.see_also.keys())

        for key, urls in expected_link_keys.items():
            for url in urls:
                add_url = self.see_also[url]
                if add_url and key not in has_link_keys:
                    add.append(url)
                if not add_url and url in has_links:
                    remove.append(url)

        return AddRemoveChange(add=add, remove=remove)

    def update_user_story(self, user_story: str) -> Optional[str]:
        new_user_story = []
        user_story_updates = defaultdict(list)
        for change in self.user_story:
            user_story_updates[change.field].append(change)

        has_updates = False
        applied_changes = set()

        for line, key, value in parse_user_story(user_story):
            if key is None or value is None:
                new_user_story.append(line)
                continue

            output_line: Optional[tuple[str, str]] = (key, value)
            if key in user_story_updates:
                changes = user_story_updates[key]
                current_value = value.strip()
                for change in changes:
                    if change in applied_changes:
                        continue
                    if current_value == change.old_value:
                        applied_changes.add(change)
                        if change.type == UserStoryChangeType.DELETE:
                            output_line = None
                            has_updates = True
                        elif change.type == UserStoryChangeType.REPLACE:
                            assert change.new_value is not None
                            output_line = (key, change.new_value)
                            has_updates = True
                    elif (
                        change.type == UserStoryChangeType.APPEND
                        and current_value == change.new_value
                    ):
                        # If we are going to append a value that's already there
                        # do nothing
                        applied_changes.add(change)
            if output_line is not None:
                new_user_story.append(f"{output_line[0]}:{output_line[1]}")

        for changes in user_story_updates.values():
            for change in changes:
                if change not in applied_changes:
                    if change.type == UserStoryChangeType.DELETE:
                        # Tried to delete a key that doesn't exist, do nothing
                        pass
                    elif change.type == UserStoryChangeType.REPLACE:
                        # Tried to replace a key that doesn't exist, do nothing
                        pass
                    elif change.type == UserStoryChangeType.APPEND:
                        new_user_story.append(f"{change.field}:{change.new_value}")
                        has_updates = True

        if has_updates:
            return "\n".join(new_user_story)

        return None

    def into_bugzilla_update(self, bug: Bug) -> BugzillaUpdate:
        bugzilla_update = BugzillaUpdate()

        if self.keywords:
            bugzilla_update.keywords = self.update_keywords(set(bug["keywords"]))
        if self.see_also:
            bugzilla_update.see_also = self.update_see_also(bug["url"], bug["see_also"])
        if self.user_story:
            bugzilla_update.user_story = self.update_user_story(bug["cf_user_story"])

        if self.resolve:
            if bug["resolution"] != self.resolve.value:
                bugzilla_update.status = (
                    "REOPENED" if self.resolve == Resolution.NONE else "RESOLVED"
                )
                bugzilla_update.resolution = self.resolve.value

        if self.comment and (bugzilla_update or self.comment_when_unchanged):
            bugzilla_update.comment = "\n\n".join(self.comment)

        return bugzilla_update


def url_keys(urls: Iterable[str]) -> Mapping[tuple[str, str], list[str]]:
    """Group URLs by a key consisting of their hostname and path"""
    rv: dict[tuple[str, str], list[str]] = {}
    for url in urls:
        try:
            parsed = parse.urlparse(url)
            if parsed.hostname is None:
                continue
            key = (parsed.hostname, parsed.path)
            if key not in rv:
                rv[key] = []
            rv[key].append(url)
        except ValueError:
            pass
    return rv


@dataclass
class FeatureData:
    feature: str
    supported_browsers: set[str]
    sp_issue: Optional[int]
    spec_url: set[str]

    def is_supported(self) -> bool:
        return {"firefox", "firefox_android"}.issubset(self.supported_browsers)


@dataclass
class FeatureBug:
    """Bug that represents a web-feature"""

    resolution: str
    keywords: list[str]
    url: Optional[str]
    whiteboard: str
    see_also: set[str]
    user_story: Mapping[str, str | list[str]]
    features: Mapping[str, FeatureData]

    def is_supported(self) -> bool:
        return all(feature.is_supported() for feature in self.features.values())

    def expected_keywords(self) -> set[str]:
        rv = set()
        if "[platform-feature]" in self.whiteboard:
            rv.add("web-feature")
        if not self.is_supported():
            for feature in self.features.values():
                if {"chrome", "chrome_android"}.issubset(feature.supported_browsers):
                    rv.add("parity-chrome")
                if {"safari", "safari_ios"}.issubset(feature.supported_browsers):
                    rv.add("parity-safari")
        return rv

    def missing_keywords(self) -> set[str]:
        return self.expected_keywords().difference(self.keywords)

    def expected_links(self) -> set[str]:
        links = set()
        for feature_name, feature in self.features.items():
            links.add(
                f"https://web-platform-dx.github.io/web-features-explorer/features/{feature_name}/"
            )
            if feature.sp_issue is not None:
                links.add(
                    f"https://github.com/mozilla/standards-positions/issues/{feature.sp_issue}"
                )
            links |= feature.spec_url
        return links

    def missing_links(self) -> set[str]:
        rv = set()
        has_links = list(self.see_also)
        if self.url:
            has_links.append(self.url)
        has_link_keys = url_keys(has_links)
        expected_link_keys = url_keys(self.expected_links())

        for key, urls in expected_link_keys.items():
            if key not in has_link_keys:
                rv |= set(urls)
        return rv

    def remove_links(self) -> set[str]:
        rv = set()
        for link in self.see_also:
            if link.startswith(
                "https://web-platform-dx.github.io/web-features-explorer/features/"
            ) and not any(
                link.startswith(
                    f"https://web-platform-dx.github.io/web-features-explorer/features/{feature_name}/"
                )
                for feature_name in self.features.keys()
            ):
                rv.add(link)
        return rv


_DataType = TypeVar("_DataType")


class UpdateRule(ABC, Generic[_DataType]):
    """Rule for updating bugs based on BigQuery data"""

    def __init__(self, client: bigquery.Client):
        self.client = client

    @abstractmethod
    def get_data(self) -> _DataType:
        ...

    @abstractmethod
    def update(
        self, updates: MutableMapping[int, FeatureBugUpdate], data: _DataType
    ) -> None:
        ...

    def run(self, updates: MutableMapping[int, FeatureBugUpdate]) -> None:
        data: _DataType = self.get_data()
        self.update(updates, data)


class FeatureRenames(UpdateRule):
    """Update web-feature marker for features that have been renamed"""

    def get_data(self) -> Mapping[int, list[tuple[str, str]]]:
        rv = defaultdict(list)
        query = """
    SELECT DISTINCT number, feature, redirect_target
    FROM `web_features.features_moved`
    JOIN `webcompat_knowledge_base.bugzilla_bugs` AS bugs
      ON feature IN UNNEST(`webcompat_knowledge_base.EXTRACT_ARRAY`(bugs.user_story, "$.web-feature"))"""

        for row in self.client.query(query):
            rv[row.number].append((row["feature"], row["redirect_target"]))

        return rv

    def update(
        self,
        updates: MutableMapping[int, FeatureBugUpdate],
        data: Mapping[int, list[tuple[str, str]]],
    ) -> None:
        for bug_id, renames in data.items():
            for old_name, new_name in renames:
                updates[bug_id].user_story.append(
                    UserStoryChange(
                        "web-feature", UserStoryChangeType.REPLACE, old_name, new_name
                    )
                )


class InvalidFeatures(UpdateRule):
    def get_data(self) -> Mapping[int, list[tuple[str, list[str]]]]:
        rv = defaultdict(list)
        query = """
    WITH
    missing_features AS (
      SELECT number, bug_feature as bug_feature
      FROM `webcompat_knowledge_base.bugzilla_bugs` AS bugs
      JOIN UNNEST(`webcompat_knowledge_base.EXTRACT_ARRAY`(bugs.user_story, "$.web-feature")) AS bug_feature
      LEFT JOIN `web_features.features_latest` AS features ON features.feature = bug_feature
      LEFT JOIN `web_features.features_moved` AS moved ON moved.feature = bug_feature
      WHERE features.feature IS NULL AND moved.feature IS NULL
    ),

    suggestions AS (
      SELECT number, bug_feature, feature, EDIT_DISTANCE(feature, bug_feature) as distance
      FROM missing_features
      CROSS JOIN `web_features.features_latest`
    )

    SELECT number, bug_feature, ARRAY_AGG(STRUCT(feature as feature, distance) ORDER BY distance LIMIT 5) AS suggestions
    FROM suggestions
    WHERE distance < 5
    GROUP BY number, bug_feature
    """
        for row in self.client.query(query):
            rv[row.number].append(
                (
                    row.bug_feature,
                    [
                        suggestion["feature"]
                        for suggestion in sorted(
                            row.suggestions, key=lambda x: x["distance"]
                        )
                    ],
                )
            )

        return rv

    def update(
        self,
        updates: MutableMapping[int, FeatureBugUpdate],
        data: Mapping[int, list[tuple[str, list[str]]]],
    ) -> None:
        for bug_id, invalid_names in data.items():
            for invalid_name, suggestions in invalid_names:
                updates[bug_id].user_story.append(
                    UserStoryChange(
                        "web-feature", UserStoryChangeType.DELETE, invalid_name
                    )
                )
                options_links = [
                    f"[{suggestion}](https://web-platform-dx.github.io/web-features-explorer/features/{suggestion})"
                    for suggestion in suggestions
                ]
                # TODO: Consider adding a needinfo on someone (reporter? user that added this?)
                comment = f"{invalid_name} is not a valid web-feature id."
                if options_links:
                    comment += f" Consider one of the following possible ids: {', '.join(options_links)}."
                updates[bug_id].comment.append(comment)


class UpdateMetadata(UpdateRule):
    """Update existing web-feature bugs to ensure they have the correct metadata and status"""

    def get_data(self) -> Mapping[int, FeatureBug]:
        rv: dict[int, FeatureBug] = {}
        query = """
WITH
feature_bugs AS (
  SELECT
    number,
    ARRAY_AGG(STRUCT(
      feature,
      web_features.spec as spec_url,
      (SELECT ARRAY_AGG(browser) FROM UNNEST(web_features.support)) AS supported_browsers,
      sp_mozilla.issue as sp_issue
      )
    ) as features,
    LOGICAL_OR(
      bugs.resolution = "FIXED" AND
      ("firefox" NOT in UNNEST(web_features.support.browser) OR
       "firefox_android" NOT IN UNNEST(web_features.support.browser))
    ) as unsupported_closed_bug
  FROM `webcompat_knowledge_base.bugzilla_bugs` AS bugs
  JOIN `web_features.features_latest` AS web_features
    ON web_features.feature IN UNNEST(`webcompat_knowledge_base.EXTRACT_ARRAY`(bugs.user_story, "$.web-feature"))
  LEFT JOIN `standards_positions.mozilla_standards_positions` AS sp_mozilla
    ON (`webcompat_knowledge_base.BUG_ID_FROM_BUGZILLA_URL`(sp_mozilla.bug) = bugs.number OR sp_mozilla.web_feature = feature)
  GROUP BY number
)

SELECT
    number,
    resolution,
    url,
    keywords,
    whiteboard,
    see_also,
    user_story,
    features
FROM feature_bugs
JOIN `webcompat_knowledge_base.bugzilla_bugs` AS bugs USING(number)
WHERE
  ("web-feature" in UNNEST(keywords) OR whiteboard LIKE "%[platform-feature]%") AND
  (resolution = "" OR unsupported_closed_bug)
"""

        for row in self.client.query(query):
            rv[row.number] = FeatureBug(
                resolution=row.resolution,
                url=row.url,
                keywords=row.keywords,
                whiteboard=row.whiteboard,
                see_also=set(row.see_also),
                user_story=row.user_story,
                features={
                    feature["feature"]: FeatureData(
                        feature=feature["feature"],
                        spec_url=set(feature["spec_url"]),
                        supported_browsers=set(feature["supported_browsers"]),
                        sp_issue=feature["sp_issue"],
                    )
                    for feature in row.features
                },
            )

        return rv

    def update(
        self,
        updates: MutableMapping[int, FeatureBugUpdate],
        data: Mapping[int, FeatureBug],
    ) -> None:
        for bug_id, feature_bug in data.items():
            # Add any missing keywords
            # TODO: are there keywords we should remove too if they're invalid
            for keyword in feature_bug.missing_keywords():
                updates[bug_id].keywords[keyword] = True
            for link in feature_bug.missing_links():
                updates[bug_id].see_also[link] = True
            for link in feature_bug.remove_links():
                updates[bug_id].see_also[link] = False

            # Close bugs where the BCD status is fixed
            if (
                feature_bug.resolution == ""
                and "leave-open" not in feature_bug.keywords
                and feature_bug.is_supported()
            ):
                updates[bug_id].resolve = Resolution.FIXED

            # Reopen bugs where the BCD status is not fixed
            unsupported_features = [
                feature.feature
                for feature in feature_bug.features.values()
                if not feature.is_supported()
            ]
            if feature_bug.resolution == "FIXED" and unsupported_features:
                updates[bug_id].resolve = Resolution.NONE
                feature_list = ", ".join(
                    f"{feature_name} ([definition file](https://github.com/web-platform-dx/web-features/blob/main/features/{feature_name}.yml.dist))"
                    for feature_name in unsupported_features
                )
                text = (
                    f"web-features {feature_list} are"
                    if len(unsupported_features) > 1
                    else f"web-feature {feature_list} is"
                )
                updates[bug_id].comment.append(
                    f"""Bug was resolved, but the {text} not yet marked as supported in Firefox.

Feature bugs are usually automatically closed once the corresponding web-features are marked as supported; this typically happens after the feature reaches release.
"""
                )


class WebPlatformFeatures(BzCleaner):
    def __init__(self) -> None:
        super().__init__()
        self.bug_updates: dict[int, FeatureBugUpdate] = defaultdict(FeatureBugUpdate)

    def description(self) -> str:
        return "Update web-features bugs"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

    def columns(self) -> list[str]:
        return ["id", "summary", "changes", "whiteboard", "user_story"]

    def handle_bug(self, bug: Bug, data: dict[str, Any]) -> Optional[Bug]:
        bug_id_str = str(bug["id"])
        bug_id_int = int(bug["id"])

        if bug_id_int not in self.bug_updates:
            return None
        bugzilla_update = self.bug_updates[bug_id_int].into_bugzilla_update(bug)

        if bugzilla_update:
            self.autofix_changes[bug_id_str] = bugzilla_update.to_json()
            data[bug_id_str] = {
                "changes": bugzilla_update,
                "whiteboard": bug["whiteboard"],
                "user_story": bug["cf_user_story"],
            }
            return bug

        return None

    def get_bz_params(self, date: str) -> dict[str, str | int | list[str] | list[int]]:
        fields = [
            "id",
            "url",
            "see_also",
            "keywords",
            "whiteboard",
            "cf_user_story",
            "status",
            "resolution",
        ]
        self.get_bug_updates()
        return {"include_fields": fields, "id": list(self.bug_updates.keys())}

    def get_bug_updates(self) -> None:
        project = "moz-fx-dev-dschubert-wckb"
        client = gcp.get_bigquery_client(project, ["cloud-platform", "drive"])
        for update_rule in [
            FeatureRenames(client),
            InvalidFeatures(client),
            UpdateMetadata(client),
        ]:
            update_rule.run(self.bug_updates)


if __name__ == "__main__":
    WebPlatformFeatures().run()
