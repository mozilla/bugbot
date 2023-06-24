# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools
from datetime import timedelta
from functools import cached_property
from typing import Iterable, Iterator

from libmozdata import bugzilla, clouseau, socorro
from libmozdata import utils as lmdutils

from bugbot.components import ComponentName
from bugbot.crash import socorro_util


class NoCrashReportFoundError(Exception):
    """Raised when no crash report is found with the required criteria."""


class ClouseauReportsAnalyzer:
    REGRESSOR_MINIMUM_SCORE: int = 8

    def __init__(self, reports: Iterable[dict]):
        self._clouseau_reports = reports

    @cached_property
    def max_score(self):
        if not self._clouseau_reports:
            return 0
        return max(report["max_score"] for report in self._clouseau_reports)

    @cached_property
    def regressed_by_potential_bug_ids(self) -> set[int]:
        minimum_accepted_score = max(self.REGRESSOR_MINIMUM_SCORE, self.max_score)
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
        minimum_accepted_score = max(self.REGRESSOR_MINIMUM_SCORE, self.max_score)
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
        bug_ids = self.regressed_by_potential_bug_ids
        if len(bug_ids) == 1:
            return next(iter(bug_ids))
        return None

    @cached_property
    def regressed_by_potential_bugs(self) -> list[dict]:
        def handler(bug: dict, data: list):
            data.append(bug)

        bugs: list[dict] = []
        bugzilla.Bugzilla(
            bugids=self.regressed_by_potential_bug_ids,
            include_fields=[
                "id",
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
        if not self.regressed_by:
            return None

        bug = self.regressed_by_potential_bugs[0]
        assert bug["id"] == self.regressed_by
        return bug["assigned_to_detail"]

    @cached_property
    def crash_component(self) -> ComponentName:
        potential_components = {
            ComponentName(bug["product"], bug["component"])
            for bug in self.regressed_by_potential_bugs
        }
        if len(potential_components) == 1:
            return next(iter(potential_components))
        return ComponentName("Core", "General")


class SocorroInfoAnalyzer(socorro_util.SignatureStats):
    __bugzilla_os_legal_values = None
    __bugzilla_cpu_legal_values_map = None

    @classmethod
    def to_bugzilla_op_sys(cls, op_sys: str) -> str:
        if cls.__bugzilla_os_legal_values is None:
            cls.__bugzilla_os_legal_values = set(
                bugzilla.BugFields.fetch_field_values("op_sys")
            )

        if op_sys in cls.__bugzilla_os_legal_values:
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
        all_op_sys = {
            self.to_bugzilla_op_sys(op_sys["term"])
            for op_sys in self.signature["facets"]["platform_pretty_version"]
        }

        if len(all_op_sys) > 1:
            # TODO: explain this workaround
            all_op_sys = {op_sys.split(" ")[0] for op_sys in all_op_sys}

        if len(all_op_sys) == 2 and "Other" in all_op_sys:
            all_op_sys.remove("Other")

        if len(all_op_sys) == 1:
            return next(iter(all_op_sys))

        if len(all_op_sys) == 0:
            return "Unspecified"

        return "All"

    @classmethod
    def to_bugzilla_cpu(cls, cpu: str) -> str:
        if cls.__bugzilla_cpu_legal_values_map is None:
            cls.__bugzilla_cpu_legal_values_map = {
                value.lower(): value
                for value in bugzilla.BugFields.fetch_field_values("rep_platform")
            }

        return cls.__bugzilla_cpu_legal_values_map.get(cpu, "Other")

    @property
    def bugzilla_cpu_arch(self) -> str:
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
    def num_user_comments(self) -> int:
        # TODO: count useful/intrusting user comments (e.g., exclude one word comments)
        return self.signature["facets"]["cardinality_user_comments"]["value"]

    @property
    def has_user_comments(self) -> bool:
        return self.num_user_comments > 0

    @property
    def top_proto_signature(self) -> str:
        return self.signature["facets"]["proto_signature"][0]["term"]

    @property
    def num_top_proto_signature_crashes(self) -> int:
        return self.signature["facets"]["proto_signature"][0]["count"]

    @property
    def build_ids(self) -> Iterator[int]:
        for build_id in self.signature["facets"]["build_id"]:
            yield build_id["term"]

    @property
    def top_build_id(self) -> int:
        return self.signature["facets"]["build_id"][0]["term"]


class SignatureAnalyzer(SocorroInfoAnalyzer, ClouseauReportsAnalyzer):
    platforms = [
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
        clouseau_reports: list[dict],
    ):
        SocorroInfoAnalyzer.__init__(
            self, signature, num_total_crashes, platforms=self.platforms
        )
        ClouseauReportsAnalyzer.__init__(self, clouseau_reports)

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

    def fetch_representing_processed_crash(self) -> dict:
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
            self._fetch_crash_reports(self.top_proto_signature, self.build_ids),
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


class SignaturesDataFetcher:
    def __init__(
        self,
        signatures,
        product: str = "Firefox",
        channel: str = "nightly",
    ):
        self._signatures = signatures
        self._product = product
        self._channel = channel

    def fetch_clouseau_crash_reports(self) -> dict[str, list]:
        return clouseau.Reports.get_by_signatures(
            self._signatures,
            product=self._product,
            channel=self._channel,
        )

    def fetch_socorro_info(self) -> tuple[list[dict], int]:
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

        return data["signatures"], data["num_total_crashes"]

    def analyze(self) -> list[SignatureAnalyzer]:
        clouseau_reports = self.fetch_clouseau_crash_reports()
        signatures, num_total_crashes = self.fetch_socorro_info()

        return [
            SignatureAnalyzer(
                signature,
                num_total_crashes,
                clouseau_reports[signature["term"]],
            )
            for signature in signatures
            # TODO(investigate): For now, we are ignoring signatures that are
            # not analyzed by clouseau. We should investigate why they are not
            # analyzed and whether we should include them.
            if signature["term"] in clouseau_reports
        ]
