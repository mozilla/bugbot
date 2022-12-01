# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Set, Union

import libmozdata.socorro as socorro
from libmozdata import utils as lmdutils
from libmozdata import versions as lmdversions

from auto_nag.scripts.no_crashes import NoCrashes


class SocorroError(Exception):
    pass


def _format_criteria_names(criteria: List[dict]):
    return [
        {
            **criterion,
            "name": "Top {tc_limit} {name} on {channel}".format(**criterion),
        }
        for criterion in criteria
    ]


# Top crash identification criteria as defined on Mozilla Wiki.
#
# Wiki page: https://wiki.mozilla.org/CrashKill/Topcrash

TOP_CRASH_IDENTIFICATION_CRITERIA = _format_criteria_names(
    [
        # -------
        # Firefox
        # -------
        {
            "name": "desktop browser crashes",
            "product": "Firefox",
            "channel": "release",
            "tc_limit": 20,
            "tc_startup_limit": 30,
        },
        {
            "name": "desktop browser crashes",
            "product": "Firefox",
            "channel": "beta",
            "tc_limit": 20,
            "tc_startup_limit": 30,
        },
        {
            "name": "desktop browser crashes",
            "product": "Firefox",
            "channel": "nightly",
            "minimum_installations": 5,
            "tc_limit": 10,
        },
        {
            "name": "content process crashes",
            "product": "Firefox",
            "channel": "beta",
            "process_type": "content",
            "tc_limit": 10,
        },
        {
            "name": "content process crashes",
            "product": "Firefox",
            "channel": "release",
            "process_type": "content",
            "tc_limit": 10,
        },
        {
            "name": "GPU process crashes",
            "product": "Firefox",
            "channel": "beta",
            "process_type": "gpu",
            "tc_limit": 5,
        },
        {
            "name": "GPU process crashes",
            "product": "Firefox",
            "channel": "release",
            "process_type": "gpu",
            "tc_limit": 5,
        },
        {
            "name": "RDD process crashes",
            "product": "Firefox",
            "channel": "beta",
            "process_type": "rdd",
            "tc_limit": 5,
        },
        {
            "name": "RDD process crashes",
            "product": "Firefox",
            "channel": "release",
            "process_type": "rdd",
            "tc_limit": 5,
        },
        {
            "name": "socket and utility process crashes",
            "product": "Firefox",
            "channel": "beta",
            "process_type": ["socket", "utility"],
            "tc_limit": 5,
        },
        {
            "name": "socket and utility process crashes",
            "product": "Firefox",
            "channel": "release",
            "process_type": ["socket", "utility"],
            "tc_limit": 5,
        },
        {
            "name": "desktop browser crashes on Linux",
            "product": "Firefox",
            "channel": "beta",
            "platform": "Linux",
            "minimum_installations": 3,
            "tc_limit": 5,
        },
        {
            "name": "desktop browser crashes on Linux",
            "product": "Firefox",
            "channel": "release",
            "platform": "Linux",
            "minimum_installations": 3,
            "tc_limit": 5,
        },
        {
            "name": "desktop browser crashes on Mac",
            "product": "Firefox",
            "channel": "beta",
            "platform": "Mac OS X",
            "minimum_installations": 3,
            "tc_limit": 5,
        },
        {
            "name": "desktop browser crashes on Mac",
            "product": "Firefox",
            "channel": "release",
            "platform": "Mac OS X",
            "minimum_installations": 3,
            "tc_limit": 5,
        },
        {
            "name": "desktop browser crashes on Windows",
            "product": "Firefox",
            "channel": "beta",
            "platform": "Windows",
            "minimum_installations": 3,
            "tc_limit": 5,
        },
        {
            "name": "desktop browser crashes on Windows",
            "product": "Firefox",
            "channel": "release",
            "platform": "Windows",
            "minimum_installations": 3,
            "tc_limit": 5,
        },
        # -----
        # Fenix
        # -----
        {
            "name": "AArch64 and ARM crashes",
            "product": "Fenix",
            "channel": "nightly",
            "cpu_arch": ["arm64", "arm"],
            "tc_limit": 10,
        },
        {
            "name": "AArch64 and ARM crashes",
            "product": "Fenix",
            "channel": "beta",
            "cpu_arch": ["arm64", "arm"],
            "tc_limit": 10,
        },
        {
            "name": "AArch64 and ARM crashes",
            "product": "Fenix",
            "channel": "release",
            "cpu_arch": ["arm64", "arm"],
            "tc_limit": 10,
        },
    ]
)

# The crash signature block patterns are based on the criteria defined on
# Mozilla Wiki. However, the matching roles (e.g., `!=` and `!^`) are based on
# the SuperSearch docs.
#
# Wiki page: https://wiki.mozilla.org/CrashKill/Topcrash
# Docs: https://crash-stats.mozilla.org/documentation/supersearch/#operators
CRASH_SIGNATURE_BLOCK_PATTERNS = [
    "!^EMPTY: ",
    "!^OOM ",
    "!=IPCError-browser | ShutDownKill",
    "!^java.lang.OutOfMemoryError",
]


class Topcrash:
    def __init__(
        self,
        date: Union[str, datetime] = "today",
        duration: int = 7,
        minimum_crashes: int = 15,
        signature_block_patterns: list = CRASH_SIGNATURE_BLOCK_PATTERNS,
        criteria: Iterable[dict] = TOP_CRASH_IDENTIFICATION_CRITERIA,
    ) -> None:
        """Constructor

        Args:
            date: the final date. If not provided, the value will be today.
            duration: the number of days to retrieve the crash data.
            minimum_crashes: the minimum number of crashes to consider a
                signature in the top crashes.
            signature_block_list: a list of crash signature to be ignored.
            criteria: the list of criteria to be used to query the top crashes.
        """
        self.minimum_crashes = minimum_crashes
        self.signature_block_patterns = signature_block_patterns
        self.criteria = criteria

        end_date = lmdutils.get_date_ymd(date)
        self.start_date = lmdutils.get_date_ymd(end_date - timedelta(duration))
        self.date_range = socorro.SuperSearch.get_search_date(self.start_date, end_date)

        self._blocked_signatures: Optional[Set[str]] = None
        self.__version_constrains: Optional[Dict[str, str]] = None

    def _fetch_signatures_from_patterns(self, patterns) -> Set[str]:
        MAX_SIGNATURES_IN_REQUEST = 1000

        signatures: Set[str] = set()
        params = {
            "date": self.date_range,
            "signature": [
                pattern if pattern[0] != "!" else pattern[1:] for pattern in patterns
            ],
            "_results_number": 0,
            "_facets_size": MAX_SIGNATURES_IN_REQUEST,
        }

        def handler(search_resp: dict, data: set):
            data.update(
                signature["term"]
                for signature in search_resp["facets"]["signature"]
                if signature["count"] >= self.minimum_crashes
            )

        socorro.SuperSearch(
            params=params,
            handler=handler,
            handlerdata=signatures,
        ).wait()

        assert (
            len(signatures) < MAX_SIGNATURES_IN_REQUEST
        ), "the patterns match more signatures than what the request could return, consider to increase the threshold"

        return signatures

    def fetch_signature_volume(
        self,
        signatures: Iterable[str],
    ) -> dict:
        """Fetch the volume of crashes for each crash signature.

        Returns:
            A dictionary with the crash signature as key and the volume as value.
        """

        def handler(search_resp: dict, data: dict):
            if search_resp["errors"]:
                raise SocorroError(search_resp["errors"])

            data.update(
                {
                    signature["term"]: signature["count"]
                    for signature in search_resp["facets"]["signature"]
                }
            )

        signature_volume: dict = {signature: 0 for signature in signatures}
        assert len(signature_volume) > 0, "no signatures provided"

        chunks, size = NoCrashes.chunkify(
            ["=" + signature for signature in signature_volume]
        )
        searches = [
            socorro.SuperSearch(
                params={
                    "date": self.date_range,
                    "signature": _signatures,
                    "_facets": "signature",
                    "_results_number": 0,
                    "_facets_size": size,
                },
                handler=handler,
                handlerdata=signature_volume,
            )
            for _signatures in chunks
        ]

        for search in searches:
            search.wait()

        return signature_volume

    def get_blocked_signatures(self) -> Set[str]:
        """Return the list of signatures to be ignored."""
        if self._blocked_signatures is None:
            self._blocked_signatures = self._fetch_signatures_from_patterns(
                self.signature_block_patterns
            )

        return self._blocked_signatures

    def get_signatures(
        self,
    ) -> Dict[str, List[dict]]:
        """Fetch the top crashes from socorro.

        Top crashes will be queried twice for each release channel, one that
        targets startup crashes and another that targets all crashes.

        Returns:
            A dictionary where the keys are crash signatures, and the values are
            list of criteria that the crash signature matches.
        """

        data: dict = defaultdict(dict)
        searches = [
            socorro.SuperSearch(
                params=self.__get_params_from_criterion(criterion),
                handler=self.__signatures_handler(criterion),
                handlerdata=data[criterion["name"]],
            )
            for criterion in self.criteria
        ]

        for search in searches:
            search.wait()

        # We merge the results after finishing all queries to avoid race conditions
        result = {}
        for _, signatures in data.items():
            for signature_name, signature_info in signatures.items():
                if signature_name not in result:
                    result[signature_name] = [signature_info]
                else:
                    result[signature_name].append(signature_info)

        return result

    def __get_params_from_criterion(self, criterion: dict):
        params = {
            "product": criterion["product"],
            "release_channel": criterion["channel"],
            "major_version": self._get_major_version_constrain(criterion["channel"]),
            "process_type": criterion.get("process_type"),
            "cpu_arch": criterion.get("cpu_arch"),
            "platform": criterion.get("platform"),
            "date": self.date_range,
            "_aggs.signature": [
                "_cardinality.install_time",
                "startup_crash",
            ],
            "_results_number": 0,
            "_facets_size": (
                criterion.get("tc_startup_limit", criterion["tc_limit"])
                # Because of the limitation in https://bugzilla.mozilla.org/show_bug.cgi?id=1257376#c9,
                # we cannot ignore the generic signatures in the Socorro side, thus we ignore them
                # in the client side. We add here the maximum number of signatures that could be
                # ignored to stay in the safe side.
                + len(self.get_blocked_signatures())
            ),
        }
        return params

    def _get_major_version_constrain(self, channel: str) -> str:
        """Return the major version constrain for the given channel."""
        if self.__version_constrains is None:
            versions = lmdversions.get(base=True)
            last_release_date = lmdversions.getMajorDate(versions["release"])

            if last_release_date > self.start_date:
                # If the release date is newer than the start date in the query, we
                # include an extra version to have enough data.
                self.__version_constrains = {
                    "nightly": f""">={versions["nightly"]-1}""",
                    "beta": f""">={versions["beta"]-1}""",
                    "release": f""">={versions["release"]-1}""",
                }
            else:
                self.__version_constrains = {
                    "nightly": f""">={versions["nightly"]}""",
                    "beta": f""">={versions["beta"]}""",
                    "release": f""">={versions["release"]}""",
                }

        return self.__version_constrains[channel]

    @staticmethod
    def __is_startup_crash(signature: dict):
        return any(
            startup["term"] == "T" for startup in signature["facets"]["startup_crash"]
        )

    def __signatures_handler(self, criterion: dict):
        def handler(search_resp: dict, data: dict):
            """
            Handle and merge crash signatures from different queries.

            Only startup crashes will be considered after exceeding `tc_limit`
            and up to `tc_startup_limit`.
            """

            blocked_signatures = self.get_blocked_signatures()

            signatures = search_resp["facets"]["signature"]
            tc_limit = criterion["tc_limit"]
            tc_startup_limit = criterion.get("tc_startup_limit", tc_limit)
            minimum_installations = criterion.get("minimum_installations", 3)
            assert tc_startup_limit >= tc_limit

            rank = 0
            for signature in signatures:
                if (
                    rank >= tc_startup_limit
                    or signature["count"] < self.minimum_crashes
                ):
                    return

                name = signature["term"]
                installations = signature["facets"]["cardinality_install_time"]["value"]
                if installations < minimum_installations or name in blocked_signatures:
                    continue

                is_startup = self.__is_startup_crash(signature)
                if is_startup or rank < tc_limit:
                    data[name] = {
                        "criterion_name": criterion["name"],
                        "is_startup": is_startup,
                    }

                rank += 1

        return handler
