# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from functools import cached_property
from typing import Any, Iterable, NamedTuple

from libmozdata import versions as lmdversions
from libmozdata.bugzilla import Bugzilla

from bugbot import utils
from bugbot.components import ComponentName


class VersionStatus(NamedTuple):
    """A representation of a version status flag"""

    channel: str
    version: int
    status: str

    @property
    def flag(self) -> str:
        return utils.get_flag(self.version, "status", self.channel)


class BugAnalyzer:
    """A class to analyze a bug"""

    def __init__(self, bug: dict, store: "BugsStore"):
        """Constructor

        Args:
            bug: The bug to analyze
            store: The store of bugs
        """
        self._bug = bug
        self._store = store

    @property
    def id(self) -> int:
        """The bug id."""
        return self._bug["id"]

    @property
    def component(self) -> ComponentName:
        """The component that the bug is in."""
        return ComponentName(self._bug["product"], self._bug["component"])

    @property
    def is_security(self) -> bool:
        """Whether the bug is a security bug."""
        return any("core-security" in group for group in self._bug["groups"])

    @property
    def regressed_by_bugs(self) -> list["BugAnalyzer"]:
        """The bugs that regressed the bug."""
        return [
            self._store.get_bug_by_id(bug_id) for bug_id in self._bug["regressed_by"]
        ]

    @property
    def oldest_fixed_firefox_version(self) -> int | None:
        """The oldest version of Firefox that was fixed by this bug."""
        fixed_versions = sorted(
            int(key[len("cf_status_firefox") :])
            for key, value in self._bug.items()
            if key.startswith("cf_status_firefox")
            and "esr" not in key
            and value in ("fixed", "verified")
        )

        if not fixed_versions:
            return None

        return fixed_versions[0]

    @property
    def latest_firefox_version_status(self) -> str | None:
        """The version status for the latest version of Firefox.

        The latest version is the highest version number that has a status flag
        set (not `---`).
        """
        versions_status = sorted(
            (int(key[len("cf_status_firefox") :]), value)
            for key, value in self._bug.items()
            if value != "---"
            and key.startswith("cf_status_firefox")
            and "esr" not in key
        )

        if not versions_status:
            return None

        return versions_status[-1][1]

    def get_field(self, field: str) -> Any:
        """Get a field value from the bug.

        Args:
            field: The field name.

        Returns:
            The field value. If the field is not found, `None` is returned.
        """
        return self._bug.get(field)

    def detect_version_status_updates(self) -> list[VersionStatus]:
        """Detect the status for the version flags that should be updated.

        The status of the version flags is determined by the status of the
        regressor bug.

        Returns:
            A list of `VersionStatus` objects.
        """
        if len(self._bug["regressed_by"]) > 1:
            # Currently only bugs with one regressor are supported
            return []

        regressor_bug = self.regressed_by_bugs[0]
        regressed_version = regressor_bug.oldest_fixed_firefox_version
        if not regressed_version:
            return []

        fixed_version = self.oldest_fixed_firefox_version

        # If the latest status flag is wontfix or fix-optional, we ignore
        # setting flags with the status "affected" to newer versions.
        is_latest_wontfix = self.latest_firefox_version_status in (
            "wontfix",
            "fix-optional",
        )

        flag_updates = []
        for flag, channel, version in self._store.current_version_flags:
            if flag not in self._bug and channel == "esr":
                # It is okay if an ESR flag is absent (we try two, the current
                # and the previous). However, the absence of other flags is a
                # sign of something wrong.
                continue
            if self._bug[flag] != "---":
                # We don't override existing flags
                # XXX maybe check for consistency?
                continue
            if fixed_version and fixed_version <= version:
                # Bug was fixed in an earlier version, don't set the flag
                continue
            if (
                version >= regressed_version
                # ESR: If the regressor was uplifted, so the regression affects
                # this version.
                or regressor_bug.get_field(flag) in ("fixed", "verified")
            ):
                if is_latest_wontfix:
                    continue

                flag_updates.append(VersionStatus(channel, version, "affected"))
            else:
                flag_updates.append(VersionStatus(channel, version, "unaffected"))

        return flag_updates


class BugNotInStoreError(LookupError):
    """The bug was not found the bugs store."""


class BugsStore:
    """A class to retrieve bugs."""

    def __init__(self, bugs: Iterable[dict] = (), versions_map: dict[str, int] = None):
        self.bugs = {bug["id"]: BugAnalyzer(bug, self) for bug in bugs}
        self.versions_map = versions_map

    def get_bug_by_id(self, bug_id: int) -> BugAnalyzer:
        """Get a bug by its id.

        Args:
            bug_id: The id of the bug to retrieve.

        Returns:
            A `BugAnalyzer` object representing the bug.

        Raises:
            BugNotFoundError: The bug was not found in the store.
        """
        try:
            return self.bugs[bug_id]
        except KeyError as error:
            raise BugNotInStoreError(f"Bug {bug_id} is not the bugs store") from error

    def fetch_regressors(self, include_fields: list[str] = None):
        """Fetches the regressors for all the bugs in the store.

        Args:
            include_fields: The fields to include when fetching the bugs.
        """
        bug_ids = (
            bug_id
            for bug in self.bugs.values()
            if bug.get_field("regressed_by")
            for bug_id in bug.get_field("regressed_by")
        )

        self.fetch_bugs(bug_ids, include_fields)

    def fetch_bugs(self, bug_ids: Iterable[int], include_fields: list[str] = None):
        """Fetches the bugs from Bugzilla.

        Args:
            bug_ids: The ids of the bugs to fetch.
            include_fields: The fields to include when fetching the bugs.
        """
        bug_ids = {
            bug_id
            for bug_id in bug_ids
            # TODO: We only fetch bugs that aren't already in the store.
            # However, the new fetch request might be specifying fields that
            # aren't in the existing bug. We need at some point to handle such
            # cases (currently, we do not have this requirement).
            if bug_id not in self.bugs
        }
        if not bug_ids:
            return

        def bug_handler(bugs):
            for bug in bugs:
                self.bugs[bug["id"]] = BugAnalyzer(bug, self)

        Bugzilla(bug_ids, bughandler=bug_handler, include_fields=include_fields).wait()

    @cached_property
    def current_version_flags(self) -> list[tuple[str, str, int]]:
        """The current version flags."""
        active_versions = []

        channel_version_map = (
            self.versions_map if self.versions_map else lmdversions.get(base=True)
        )
        for channel in ("release", "beta", "nightly"):
            version = int(channel_version_map[channel])
            flag = utils.get_flag(version, "status", channel)
            active_versions.append((flag, channel, version))

        esr_versions = {
            channel_version_map["esr"],
            channel_version_map["esr_previous"],
        }
        for version in esr_versions:
            channel = "esr"
            flag = utils.get_flag(version, "status", channel)
            active_versions.append((flag, channel, version))

        return active_versions
