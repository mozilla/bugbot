# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools
import re
from collections import defaultdict
from datetime import date, timedelta
from functools import cached_property
from typing import Iterable, Iterator

from libmozdata import bugzilla, clouseau, connection, socorro
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla
from libmozdata.connection import Connection

from bugbot import logger, utils
from bugbot.components import ComponentName
from bugbot.crash import socorro_util

# The max offset from a memory address to be considered "near".
OFFSET_64_BIT = 0x1000
OFFSET_32_BIT = 0x100
# Allocator poison value addresses.
ALLOCATOR_ADDRESSES_64_BIT = (
    (0xE5E5E5E5E5E5E5E5, OFFSET_64_BIT),
    # On 64-bit windows, sometimes it could be doing something with a 32-bit
    # value gotten from freed memory, so it'll be 0X00000000E5E5E5E5 +/-, and
    # because of the address limitation, quite often it will be
    # 0X0000E5E5E5E5E5E5 +/-.
    (0x00000000E5E5E5E5, OFFSET_32_BIT),
    (0x0000E5E5E5E5E5E5, OFFSET_64_BIT),
    (0x4B4B4B4B4B4B4B4B, OFFSET_64_BIT),
)
ALLOCATOR_ADDRESSES_32_BIT = (
    (0xE5E5E5E5, OFFSET_32_BIT),
    (0x4B4B4B4B, OFFSET_32_BIT),
)
# Ranges where addresses are considered near allocator poison values.
ALLOCATOR_RANGES_64_BIT = (
    (addr - offset, addr + offset) for addr, offset in ALLOCATOR_ADDRESSES_64_BIT
)
ALLOCATOR_RANGES_32_BIT = (
    (addr - offset, addr + offset) for addr, offset in ALLOCATOR_ADDRESSES_32_BIT
)


def is_near_null_address(str_address) -> bool:
    """Check if the address is near null.

    Args:
        str_address: The memory address to check.

    Returns:
        True if the address is near null, False otherwise.
    """
    address = int(str_address, 0)
    is_64_bit = len(str_address) >= 18

    if is_64_bit:
        return -OFFSET_64_BIT <= address <= OFFSET_64_BIT

    return -OFFSET_32_BIT <= address <= OFFSET_32_BIT


def is_near_allocator_address(str_address) -> bool:
    """Check if the address is near an allocator poison value.

    Args:
        str_address: The memory address to check.

    Returns:
        True if the address is near an allocator poison value, False otherwise.
    """
    address = int(str_address, 0)
    is_64_bit = len(str_address) >= 18

    return any(
        low <= address <= high
        for low, high in (
            ALLOCATOR_RANGES_64_BIT if is_64_bit else ALLOCATOR_RANGES_32_BIT
        )
    )


# TODO: Move this to libmozdata
def generate_signature_page_url(params: dict, tab: str) -> str:
    """Generate a URL to the signature page on Socorro

    Args:
        params: the parameters for the search query.
        tab: the page tab that should be selected.

    Returns:
        The URL of the signature page on Socorro
    """
    web_url = socorro.Socorro.CRASH_STATS_URL
    query = lmdutils.get_params_for_url(params)
    return f"{web_url}/signature/{query}#{tab}"


# NOTE: At this point, we will file bugs on bugzilla-dev. Once we are confident
# that the bug filing is working as expected, we can switch to filing bugs in
# the production instance of Bugzilla.
class DevBugzilla(Bugzilla):
    URL = "https://bugzilla-dev.allizom.org"
    API_URL = URL + "/rest/bug"
    ATTACHMENT_API_URL = API_URL + "/attachment"
    TOKEN = utils.get_login_info()["bz_api_key_dev"]


class NoCrashReportFoundError(Exception):
    """There are no crash reports that meet the required criteria."""


class ClouseauDataAnalyzer:
    """Analyze the data returned by Crash Clouseau"""

    MINIMUM_CLOUSEAU_SCORE_THRESHOLD: int = 8
    DEFAULT_CRASH_COMPONENT = ComponentName("Core", "General")

    def __init__(self, reports: Iterable[dict]):
        self._clouseau_reports = reports

    @cached_property
    def max_clouseau_score(self):
        """The maximum Clouseau score in the crash reports."""
        if not self._clouseau_reports:
            return 0
        return max(report["max_score"] for report in self._clouseau_reports)

    @cached_property
    def regressed_by_potential_bug_ids(self) -> set[int]:
        """The IDs for the bugs that their patches could have caused the crash."""
        minimum_accepted_score = max(
            self.MINIMUM_CLOUSEAU_SCORE_THRESHOLD, self.max_clouseau_score
        )
        return {
            changeset["bug_id"]
            for report in self._clouseau_reports
            if report["max_score"] >= minimum_accepted_score
            for changeset in report["changesets"]
            if changeset["max_score"] >= minimum_accepted_score
            and not changeset["is_merge"]
            and not changeset["is_backedout"]
        }

    @cached_property
    def regressed_by_patch(self) -> str | None:
        """The hash of the patch that could have caused the crash."""
        minimum_accepted_score = max(
            self.MINIMUM_CLOUSEAU_SCORE_THRESHOLD, self.max_clouseau_score
        )
        potential_patches = {
            changeset["changeset"]
            for report in self._clouseau_reports
            if report["max_score"] >= minimum_accepted_score
            for changeset in report["changesets"]
            if changeset["max_score"] >= minimum_accepted_score
            and not changeset["is_merge"]
            and not changeset["is_backedout"]
        }
        if len(potential_patches) == 1:
            return next(iter(potential_patches))
        return None

    @cached_property
    def regressed_by(self) -> int | None:
        """The ID of the bug that one of its patches could have caused
        the crash.

        If there are multiple bugs, the value will be `None`.
        """
        bug_ids = self.regressed_by_potential_bug_ids
        if len(bug_ids) == 1:
            return next(iter(bug_ids))
        return None

    @cached_property
    def regressed_by_potential_bugs(self) -> list[dict]:
        """The bugs whose patches could have caused the crash."""

        def handler(bug: dict, data: list):
            data.append(bug)

        bugs: list[dict] = []
        Bugzilla(
            bugids=self.regressed_by_potential_bug_ids,
            include_fields=[
                "id",
                "groups",
                "assigned_to",
                "product",
                "component",
            ],
            bughandler=handler,
            bugdata=bugs,
        ).wait()

        return bugs

    @cached_property
    def regressed_by_author(self) -> dict | None:
        """The author of the patch that could have caused the crash.

        If there are multiple regressors, the value will be `None`.

        The regressor bug assignee is considered as the author, even if the
        assignee is not the patch author.
        """

        if not self.regressed_by:
            return None

        bug = self.regressed_by_potential_bugs[0]
        assert bug["id"] == self.regressed_by
        return bug["assigned_to_detail"]

    @cached_property
    def crash_component(self) -> ComponentName:
        """The component that the crash belongs to.

        If there are multiple components, the value will be the default one.
        """
        potential_components = {
            ComponentName(bug["product"], bug["component"])
            for bug in self.regressed_by_potential_bugs
        }
        if len(potential_components) == 1:
            return next(iter(potential_components))
        return self.DEFAULT_CRASH_COMPONENT


class SocorroDataAnalyzer(socorro_util.SignatureStats):
    """Analyze the data returned by Socorro."""

    _bugzilla_os_legal_values = None
    _bugzilla_cpu_legal_values_map = None
    _platforms = [
        {"short_name": "win", "name": "Windows"},
        {"short_name": "mac", "name": "Mac OS X"},
        {"short_name": "lin", "name": "Linux"},
        {"short_name": "and", "name": "Android"},
        {"short_name": "unknown", "name": "Unknown"},
    ]

    def __init__(
        self,
        signature: dict,
        num_total_crashes: int,
    ):
        super().__init__(signature, num_total_crashes, platforms=self._platforms)

    @classmethod
    def to_bugzilla_op_sys(cls, op_sys: str) -> str:
        """Return the corresponding OS name in Bugzilla for the provided OS name
        from Socorro.

        If the OS name is not recognized, return "Other".
        """
        if cls._bugzilla_os_legal_values is None:
            cls._bugzilla_os_legal_values = set(
                bugzilla.BugFields.fetch_field_values("op_sys")
            )

        if op_sys in cls._bugzilla_os_legal_values:
            return op_sys

        if op_sys.startswith("OS X ") or op_sys.startswith("macOS "):
            op_sys = "macOS"
        elif op_sys.startswith("Windows"):
            op_sys = "Windows"
        elif "Linux" in op_sys or op_sys.startswith("Ubuntu"):
            op_sys = "Linux"
        else:
            op_sys = "Other"

        return op_sys

    @property
    def bugzilla_op_sys(self) -> str:
        """The name of the OS where the crash happens.

        The value is one of the legal values for Bugzilla's `op_sys` field.

        - If no OS name is found, the value will be "Unspecified".
        - If the OS name is not recognized, the value will be "Other".
        - If multiple OS names are found, the value will be "All". Unless the OS
          names can be resolved to a common name without a version. For example,
          "Windows 10" and "Windows 7" will become "Windows".
        """
        all_op_sys = {
            self.to_bugzilla_op_sys(op_sys["term"])
            for op_sys in self.signature["facets"]["platform_pretty_version"]
        }

        if len(all_op_sys) > 1:
            # Resolve to root OS name by removing the version number.
            all_op_sys = {op_sys.split(" ")[0] for op_sys in all_op_sys}

        if len(all_op_sys) == 2 and "Other" in all_op_sys:
            # TODO: explain this workaround.
            all_op_sys.remove("Other")

        if len(all_op_sys) == 1:
            return next(iter(all_op_sys))

        if len(all_op_sys) == 0:
            return "Unspecified"

        return "All"

    @classmethod
    def to_bugzilla_cpu(cls, cpu: str) -> str:
        """Return the corresponding CPU name in Bugzilla for the provided name
        from Socorro.

        If the CPU is not recognized, return "Other".
        """
        if cls._bugzilla_cpu_legal_values_map is None:
            cls._bugzilla_cpu_legal_values_map = {
                value.lower(): value
                for value in bugzilla.BugFields.fetch_field_values("rep_platform")
            }

        return cls._bugzilla_cpu_legal_values_map.get(cpu, "Other")

    @property
    def bugzilla_cpu_arch(self) -> str:
        """The CPU architecture of the devices where the crash happens.

        The value is one of the legal values for Bugzilla's `rep_platform` field.

        - If no CPU architecture is found, the value will be "Unspecified".
        - If the CPU architecture is not recognized, the value will be "Other".
        - If multiple CPU architectures are found, the value will "All".
        """
        all_cpu_arch = {
            self.to_bugzilla_cpu(cpu["term"])
            for cpu in self.signature["facets"]["cpu_arch"]
        }

        if len(all_cpu_arch) == 2 and "Other" in all_cpu_arch:
            all_cpu_arch.remove("Other")

        if len(all_cpu_arch) == 1:
            return next(iter(all_cpu_arch))

        if len(all_cpu_arch) == 0:
            return "Unspecified"

        return "All"

    @property
    def user_comments_page_url(self) -> str:
        """The URL to the Signature page on Socorro where the Comments tab is
        selected.
        """
        start_date = date.today() - timedelta(weeks=26)
        params = {
            "signature": self.signature_term,
            "date": socorro.SuperSearch.get_search_date(start_date),
        }
        return generate_signature_page_url(params, "comments")

    @property
    def num_user_comments(self) -> int:
        """The number of crash reports with user comments."""
        # TODO: count useful/interesting user comments (e.g., exclude one word comments)
        return self.signature["facets"]["cardinality_user_comments"]["value"]

    @property
    def has_user_comments(self) -> bool:
        """Whether the crash signature has any reports with a user comment."""
        return self.num_user_comments > 0

    @property
    def top_proto_signature(self) -> str:
        """The proto signature that occurs the most."""
        return self.signature["facets"]["proto_signature"][0]["term"]

    @property
    def num_top_proto_signature_crashes(self) -> int:
        """The number of crashes for the most occurring proto signature."""
        return self.signature["facets"]["proto_signature"][0]["count"]

    def _build_ids(self) -> Iterator[int]:
        """Yields the build IDs where the crash occurred."""
        for build_id in self.signature["facets"]["build_id"]:
            yield build_id["term"]

    @property
    def top_build_id(self) -> int:
        """The build ID where most crashes occurred."""
        return self.signature["facets"]["build_id"][0]["term"]

    @cached_property
    def num_near_null_crashes(self) -> int:
        """The number of crashes that occurred on addresses near null."""
        return sum(
            address["count"]
            for address in self.signature["facets"]["address"]
            if is_near_null_address(address["term"])
        )

    @property
    def is_near_null_crash(self) -> bool:
        """Whether all crashes occurred on addresses near null."""
        return self.num_near_null_crashes == self.num_crashes

    @property
    def is_potential_near_null_crash(self) -> bool:
        """Whether the signature is a potential near null crash.

        The value will be True if some but not all crashes occurred on addresses
        near null.
        """
        return not self.is_near_null_crash and self.num_near_null_crashes > 0

    @property
    def is_near_null_related_crash(self) -> bool:
        """Whether the signature is related to near null crashes.

        The value will be True if any of the crashes occurred on addresses near
        null.
        """
        return self.is_near_null_crash or self.is_potential_near_null_crash

    @cached_property
    def num_near_allocator_crashes(self) -> int:
        """The number of crashes that occurred on addresses near an allocator
        poison value.
        """
        return sum(
            address["count"]
            for address in self.signature["facets"]["address"]
            if is_near_allocator_address(address["term"])
        )

    @property
    def is_near_allocator_crash(self) -> bool:
        """Whether all crashes occurred on addresses near an allocator poison
        value.
        """
        return self.num_near_allocator_crashes == self.num_crashes

    @property
    def is_potential_near_allocator_crash(self) -> bool:
        """Whether the signature is a potential near allocator poison value
        crash.

        The value will be True if some but not all crashes occurred on addresses
        near an allocator poison value.
        """
        return not self.is_near_allocator_crash and self.num_near_allocator_crashes > 0

    @property
    def is_near_allocator_related_crash(self) -> bool:
        """Whether the signature is related to near allocator poison value
        crashes.

        The value will be True if any of the crashes occurred on addresses near
        an allocator poison value.
        """
        return self.is_near_allocator_crash or self.is_potential_near_allocator_crash


class SignatureAnalyzer(SocorroDataAnalyzer, ClouseauDataAnalyzer):
    """Analyze the data related to a signature.

    This includes data from Socorro and Clouseau.
    """

    def __init__(
        self,
        socorro_signature: dict,
        num_total_crashes: int,
        clouseau_reports: list[dict],
    ):
        SocorroDataAnalyzer.__init__(self, socorro_signature, num_total_crashes)
        ClouseauDataAnalyzer.__init__(self, clouseau_reports)

    def _fetch_crash_reports(
        self,
        proto_signature: str,
        build_id: int | Iterable[int],
        limit: int = 1,
    ) -> Iterator[dict]:
        params = {
            "proto_signature": "=" + proto_signature,
            "build_id": build_id,
            "_columns": [
                "uuid",
            ],
            "_results_number": limit,
        }

        def handler(res: dict, data: dict):
            data.update(res)

        data: dict = {}
        socorro.SuperSearch(params=params, handler=handler, handlerdata=data).wait()

        yield from data["hits"]

    def fetch_representative_processed_crash(self) -> dict:
        """Fetch a processed crash to represent the signature.

        This could fetch multiple processed crashes and return the one that is
        most likely to be useful.
        """
        limit_to_top_proto_signature = (
            self.num_top_proto_signature_crashes / self.num_crashes > 0.6
        )

        reports = itertools.chain(
            # Reports with a higher score from clouseau are more likely to be
            # useful.
            sorted(
                self._clouseau_reports,
                key=lambda report: report["max_score"],
                reverse=True,
            ),
            # Next we try find reports from the top crashing build because they
            # are likely to be representative.
            self._fetch_crash_reports(self.top_proto_signature, self.top_build_id),
            self._fetch_crash_reports(self.top_proto_signature, self._build_ids()),
        )
        for report in reports:
            uuid = report["uuid"]
            processed_crash = socorro.ProcessedCrash.get_processed(uuid)[uuid]
            if (
                not limit_to_top_proto_signature
                or processed_crash["proto_signature"] == self.top_proto_signature
            ):
                # TODO(investigate): maybe we should check if the stack is
                # corrupted (ask gsvelto or willkg about how to detect that)
                return processed_crash

        raise NoCrashReportFoundError(
            f"No crash report found with the most frequent proto signature for {self.signature_term}."
        )

    @cached_property
    def is_potential_security_crash(self) -> bool:
        """Whether the crash is related to a potential security bug.

        The value will be True if:
            - the signature is related to near allocator poison value crashes, or
            - one of the potential regressors is a security bug
        """
        return self.is_near_allocator_related_crash or any(
            any("core-security" in group for group in bug["groups"])
            for bug in self.regressed_by_potential_bugs
        )


class SignaturesDataFetcher:
    """Fetch the data related to the given signatures."""

    MEMORY_ACCESS_ERROR_REASONS = (
        # On Windows:
        "EXCEPTION_ACCESS_VIOLATION_READ",
        "EXCEPTION_ACCESS_VIOLATION_WRITE",
        "EXCEPTION_ACCESS_VIOLATION_EXEC"
        # On Linux:
        "SIGSEGV / SEGV_MAPERR",
        "SIGSEGV / SEGV_ACCERR",
    )

    EXCLUDED_MOZ_REASON_STRINGS = (
        "MOZ_CRASH(OOM)",
        "MOZ_CRASH(Out of memory)",
        "out of memory",
        "Shutdown hanging",
        # TODO(investigate): do we need to exclude signatures that their reason
        # contains `[unhandlable oom]`?
        # Example: arena_t::InitChunk | arena_t::AllocRun | arena_t::MallocLarge | arena_t::Malloc | BaseAllocator::malloc | Allocator::malloc | PageMalloc
        # "[unhandlable oom]",
    )

    # If any of the crash reason starts with any of the following, then it is
    # Network or I/O error.
    EXCLUDED_IO_ERROR_REASON_PREFIXES = (
        "EXCEPTION_IN_PAGE_ERROR_READ",
        "EXCEPTION_IN_PAGE_ERROR_WRITE",
        "EXCEPTION_IN_PAGE_ERROR_EXEC",
    )

    # TODO(investigate): do we need to exclude all these signatures prefixes?
    EXCLUDED_SIGNATURE_PREFIXES = (
        "OOM | ",
        "bad hardware | ",
        "shutdownhang | ",
    )

    def __init__(
        self,
        signatures: Iterable[str],
        product: str = "Firefox",
        channel: str = "nightly",
    ):
        self._signatures = set(signatures)
        self._product = product
        self._channel = channel

    @classmethod
    def find_new_actionable_crashes(
        cls,
        product: str,
        channel: str,
        days_to_check: int = 7,
        days_without_crashes: int = 7,
    ) -> "SignaturesDataFetcher":
        """Find new actionable crashes.

        Args:
            product: The product to check.
            channel: The release channel to check.
            days_to_check: The number of days to check for crashes.
            days_without_crashes: The number of days without crashes before the
                `days_to_check` to consider the signature new.

        Returns:
            A list of actionable signatures.
        """
        duration = days_to_check + days_without_crashes
        end_date = lmdutils.get_date_ymd("today")
        start_date = end_date - timedelta(duration)
        earliest_allowed_date = lmdutils.get_date_str(
            end_date - timedelta(days_to_check)
        )
        date_range = socorro.SuperSearch.get_search_date(start_date, end_date)

        params = {
            "product": product,
            "release_channel": channel,
            "date": date_range,
            # TODO(investigate): should we do a local filter instead of the
            # following (should we exclude the signature if one of the crashes
            # is a shutdown hang?):
            # If the `ipc_shutdown_state` or `shutdown_progress` field are
            # non-empty then it's a shutdown hang.
            "ipc_shutdown_state": "__null__",
            "shutdown_progress": "__null__",
            # TODO(investigate): should we use the following instead of the
            # local filter.
            # "oom_allocation_size": "!__null__",
            "_aggs.signature": [
                "moz_crash_reason",
                "reason",
                "_histogram.date",
                "_cardinality.install_time",
                "_cardinality.oom_allocation_size",
            ],
            "_results_number": 0,
            "_facets_size": 10000,
        }

        def handler(search_resp: dict, data: list):
            logger.debug(
                "Total of %d signatures received from Socorro",
                len(search_resp["facets"]["signature"]),
            )

            for crash in search_resp["facets"]["signature"]:
                signature = crash["term"]
                if any(
                    signature.startswith(excluded_prefix)
                    for excluded_prefix in cls.EXCLUDED_SIGNATURE_PREFIXES
                ):
                    # Ignore signatures that start with any of the excluded prefixes.
                    continue

                facets = crash["facets"]
                installations = facets["cardinality_install_time"]["value"]
                if installations <= 1:
                    # Ignore crashes that only happen on one installation.
                    continue

                first_date = facets["histogram_date"][0]["term"]
                if first_date < earliest_allowed_date:
                    # The crash is not new, skip it.
                    continue

                if any(
                    reason["term"].startswith(io_error_prefix)
                    for reason in facets["reason"]
                    for io_error_prefix in cls.EXCLUDED_IO_ERROR_REASON_PREFIXES
                ):
                    # Ignore Network or I/O error crashes.
                    continue

                if crash["count"] < 20:
                    # For signatures with low volume, having multiple types of
                    # memory errors indicates potential bad hardware crashes.
                    num_memory_error_types = sum(
                        reason["term"] in cls.MEMORY_ACCESS_ERROR_REASONS
                        for reason in facets["reason"]
                    )
                    if num_memory_error_types > 1:
                        # Potential bad hardware crash, skip it.
                        continue

                # TODO: Add a filter using the `possible_bit_flips_max_confidence`
                # field to exclude bad hardware crashes. The filed is not available yet.
                # See: https://bugzilla.mozilla.org/show_bug.cgi?id=1816669#c3

                # TODO(investigate): is this needed since we are already
                # filtering signatures that start with "OOM | "
                if facets["cardinality_oom_allocation_size"]["value"]:
                    # If one of the crashes is an OOM crash, skip it.
                    continue

                # TODO(investigate): do we need to check for the `moz_crash_reason`
                moz_crash_reasons = facets["moz_crash_reason"]
                if moz_crash_reasons and any(
                    excluded_reason in reason["term"]
                    for reason in moz_crash_reasons
                    for excluded_reason in cls.EXCLUDED_MOZ_REASON_STRINGS
                ):
                    continue

                data.append(signature)

        signatures: list = []
        socorro.SuperSearch(
            params=params,
            handler=handler,
            handlerdata=signatures,
        ).wait()

        logger.debug(
            "Total of %d signatures left after applying the filtering criteria",
            len(signatures),
        )

        return cls(signatures, product, channel)

    def fetch_clouseau_crash_reports(self) -> dict[str, list]:
        """Fetch the crash reports data from Crash Clouseau."""
        signature_reports = clouseau.Reports.get_by_signatures(
            self._signatures,
            product=self._product,
            channel=self._channel,
        )

        logger.debug(
            "Total of %d signatures received from Clouseau", len(signature_reports)
        )

        return signature_reports

    def fetch_socorro_info(self) -> tuple[list[dict], int]:
        """Fetch the signature data from Socorro."""
        # TODO(investigate): should we increase the duration to 6 months?
        duration = timedelta(weeks=1)
        end_date = lmdutils.get_date_ymd("today")
        start_date = end_date - duration
        date_range = socorro.SuperSearch.get_search_date(start_date, end_date)

        params = {
            "product": self._product,
            # TODO(investigate): should we included all release channels?
            "release_channel": self._channel,
            # TODO(investigate): should we limit based on the build date as well?
            "date": date_range,
            # TODO: split signatures into chunks to avoid very long query URLs
            "signature": ["=" + signature for signature in self._signatures],
            "_aggs.signature": [
                "address",
                "build_id",
                "cpu_arch",
                "proto_signature",
                "_cardinality.user_comments",
                "cpu_arch",
                "platform_pretty_version",
                # The following are needed for SignatureStats:
                "platform",
                "is_garbage_collecting",
                "_cardinality.install_time",
                "startup_crash",
                "_histogram.uptime",
                "process_type",
            ],
            "_results_number": 0,
            "_facets_size": 10000,
        }

        def handler(search_results: dict, data: dict):
            data["num_total_crashes"] = search_results["total"]
            data["signatures"] = search_results["facets"]["signature"]

        data: dict = {}
        socorro.SuperSearchUnredacted(
            params=params,
            handler=handler,
            handlerdata=data,
        ).wait()

        logger.debug(
            "Fetch info from Socorro for %d signatures", len(data["signatures"])
        )

        return data["signatures"], data["num_total_crashes"]

    def fetch_bugs(self, include_fields: list[str] = None) -> dict[str, list[dict]]:
        """Fetch bugs that are filed against the given signatures."""

        params_base: dict = {
            "include_fields": [
                "cf_crash_signature",
            ],
        }

        if include_fields:
            params_base["include_fields"].extend(include_fields)

        params_list = []
        for signatures_chunk in Connection.chunks(list(self._signatures), 30):
            params = params_base.copy()
            n = int(utils.get_last_field_num(params))
            params[f"f{n}"] = "OP"
            params[f"j{n}"] = "OR"
            for signature in signatures_chunk:
                n += 1
                params[f"f{n}"] = "cf_crash_signature"
                params[f"o{n}"] = "regexp"
                params[f"v{n}"] = rf"\[(@ |@){re.escape(signature)}( \]|\])"
            params[f"f{n+1}"] = "CP"
            params_list.append(params)

        signatures_bugs: dict = defaultdict(list)

        def handler(res, data):
            for bug in res["bugs"]:
                for signature in utils.get_signatures(bug["cf_crash_signature"]):
                    if signature in self._signatures:
                        data[signature].append(bug)

        Bugzilla(
            queries=[
                connection.Query(Bugzilla.API_URL, params, handler, signatures_bugs)
                for params in params_list
            ],
        ).wait()

        # TODO: remove the call to DevBugzilla after moving to production
        DevBugzilla(
            queries=[
                connection.Query(DevBugzilla.API_URL, params, handler, signatures_bugs)
                for params in params_list
            ],
        ).wait()

        logger.debug(
            "Total of %d signatures already have bugs filed", len(signatures_bugs)
        )

        return signatures_bugs

    def analyze(self) -> list[SignatureAnalyzer]:
        """Analyze the data related to the signatures."""
        bugs = self.fetch_bugs()
        # TODO(investigate): For now, we are ignoring signatures that have bugs
        # filed even if they are closed long time ago. We should investigate
        # whether we should include the ones with closed bugs. For example, if
        # the bug was closed as Fixed years ago.
        self._signatures.difference_update(bugs.keys())

        clouseau_reports = self.fetch_clouseau_crash_reports()
        # TODO(investigate): For now, we are ignoring signatures that are not
        # analyzed by clouseau. We should investigate why they are not analyzed
        # and whether we should include them.
        self._signatures.intersection_update(clouseau_reports.keys())

        signatures, num_total_crashes = self.fetch_socorro_info()
        logger.debug("Total of %d signatures will be analyzed", len(signatures))

        return [
            SignatureAnalyzer(
                signature,
                num_total_crashes,
                clouseau_reports[signature["term"]],
            )
            for signature in signatures
        ]
