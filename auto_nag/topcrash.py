# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Union

import libmozdata.socorro as socorro
from libmozdata import utils as lmdutils

# Top crash identification criteria as defined on Mozilla Wiki.
#
# Wiki page: https://wiki.mozilla.org/CrashKill/Topcrash
TOP_CRASH_IDENTIFICATION_CRITERIA = [
    # -------
    # Firefox
    # -------
    {
        "name": "Top 20 desktop browser crashes on Release",
        "product": "Firefox",
        "channel": "release",
        "tc_limit": 20,
        "tc_startup_limit": 30,
    },
    {
        "name": "Top 20 desktop browser crashes on Beta",
        "product": "Firefox",
        "channel": "beta",
        "tc_limit": 20,
        "tc_startup_limit": 30,
    },
    {
        "name": "Top 10 desktop browser crashes on Nightly",
        "product": "Firefox",
        "channel": "nightly",
        "tc_limit": 10,
    },
    {
        "name": "Top 10 content process crashes on Beta and Release",
        "product": "Firefox",
        "channel": ["beta", "release"],
        "process_type": "content",
        "tc_limit": 10,
    },
    {
        "name": "Top 5 GPU process crashes on Beta and Release",
        "product": "Firefox",
        "channel": ["beta", "release"],
        "process_type": "gpu",
        "tc_limit": 5,
    },
    {
        "name": "Top 5 RDD process crashes on Beta and Release",
        "product": "Firefox",
        "channel": ["beta", "release"],
        "process_type": "rdd",
        "tc_limit": 5,
    },
    {
        "name": "Top 5 socket and utility process crashes on Beta and Release",
        "product": "Firefox",
        "channel": ["beta", "release"],
        "process_type": ["socket", "utility"],
        "tc_limit": 5,
    },
    {
        "name": "Top 5 desktop browser crashes on Linux on Beta and Release",
        "product": "Firefox",
        "channel": ["beta", "release"],
        "platform": "Linux",
        "tc_limit": 5,
    },
    {
        "name": "Top 5 desktop browser crashes on Mac on Beta and Release",
        "product": "Firefox",
        "channel": ["beta", "release"],
        "platform": "Mac OS X",
        "tc_limit": 5,
    },
    {
        "name": "Top 5 desktop browser crashes on Windows on Beta and Release",
        "product": "Firefox",
        "channel": ["beta", "release"],
        "platform": "Windows",
        "tc_limit": 5,
    },
    # -----
    # Fenix
    # -----
    {
        "name": "Top 10 AArch64 and ARM crashes on Nightly, Beta and Release",
        "product": "Fenix",
        "channel": ["nightly", "beta", "release"],
        "cpu_arch": ["arm64", "arm"],
        "tc_limit": 10,
    },
    {
        "name": "Top 5 AMD64 and x86 crashes on Beta and Release",
        "product": "Fenix",
        "channel": ["beta", "release"],
        "cpu_arch": ["amd64", "x86"],
        "tc_limit": 5,
    },
]

# The crash signature block patterns are based on the criteria defined on
# Mozilla Wiki. However, the matching roles (e.g., `!=` and `!^`) are based on
# the SuperSearch docs.
#
# Wiki page: https://wiki.mozilla.org/CrashKill/Topcrash
# Docs: https://crash-stats.mozilla.org/documentation/supersearch/#operators
CRASH_SIGNATURE_BLOCK_PATTERNS = [
    "!^EMPTY: ",
    "!^OOM | large | EMPTY: ",
    "!=OOM | small",
    "!=IPCError-browser | ShutDownKill",
    "!^java.lang.OutOfMemoryError",
]


class Topcrash:
    def __init__(
        self,
        minimum_crashes: Optional[int] = 5,
        signature_block_patterns: list = CRASH_SIGNATURE_BLOCK_PATTERNS,
    ) -> None:
        """Constructor

        Args:
            minimum_crashes: the minimum number of crashes to consider a
                signature in the top crashes.
            signature_block_list: a list of crash signature to be ignored.
        """
        self.minimum_crashes = minimum_crashes
        self.signature_block_patterns = signature_block_patterns

    def _fetch_signatures_from_patters(self, patterns, date_range) -> Set[str]:
        MAX_SIGNATURES_IN_REQUEST = 1000
        signatures: Set[str] = set()
        params = {
            "date": date_range,
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

    def get_signatures(
        self,
        date: Union[str, datetime],
        duration: Optional[int] = 7,
    ) -> Dict[str, List[dict]]:
        """Fetch the top crashes from socorro.

        Top crashes will be queried twice for each release channel, one that
        targets startup crashes and another that targets all crashes.

        Args:
            date: the final date
            duration: the number of days to retrieve the crash data

        Returns:
            A dictionary where the keys are crash signatures, and the values are
            list of criteria that the crash signature matches.
        """

        start_date = lmdutils.get_date(date, duration)
        end_date = lmdutils.get_date(date)
        date_range = socorro.SuperSearch.get_search_date(start_date, end_date)
        self.blocked_signatures = self._fetch_signatures_from_patters(
            self.signature_block_patterns, date_range
        )

        data: dict = defaultdict(dict)
        searches = [
            socorro.SuperSearch(
                params=self.__get_params_from_criterion(date_range, criterion),
                handler=self.__signatures_handler(criterion),
                handlerdata=data[criterion["name"]],
            )
            for criterion in TOP_CRASH_IDENTIFICATION_CRITERIA
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

    def __get_params_from_criterion(self, date_range: list, criterion: dict):
        params = {
            "product": criterion["product"],
            "release_channel": criterion["channel"],
            "process_type": criterion.get("process_type"),
            "cpu_arch": criterion.get("cpu_arch"),
            "platform": criterion.get("platform"),
            "date": date_range,
            "_aggs.signature": [
                "startup_crash",
            ],
            "_results_number": 0,
            "_facets_size": (
                criterion.get("tc_startup_limit", criterion["tc_limit"])
                # Because of the limitation in https://bugzilla.mozilla.org/show_bug.cgi?id=1257376#c9,
                # we cannot ignore the generic signatures in the Socorro side, thus we ignore them
                # in the client side. We add here the maximum number of signatures that could be
                # ignored to stay in the safe side.
                + len(self.blocked_signatures)
            ),
        }
        return params

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

            signatures = search_resp["facets"]["signature"]
            tc_limit = criterion["tc_limit"]
            tc_startup_limit = criterion.get("tc_startup_limit", tc_limit)
            assert tc_startup_limit >= tc_limit

            rank = 0
            for signature in signatures:
                if (
                    rank >= tc_startup_limit
                    or signature["count"] < self.minimum_crashes
                ):
                    return

                name = signature["term"]
                if name in self.blocked_signatures:
                    continue

                is_startup = self.__is_startup_crash(signature)
                if is_startup or rank < tc_limit:
                    data[name] = {
                        "criterion_name": criterion["name"],
                        "is_startup": is_startup,
                    }

                rank += 1

        return handler
