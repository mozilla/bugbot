# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime
from typing import Dict, Optional, Union

import libmozdata.socorro as socorro
from libmozdata import utils as lmdutils

# Top crash identification criteria as defined on Mozilla Wiki.
# Reference: https://wiki.mozilla.org/CrashKill/Topcrash
TOP_CRASH_IDENTIFICATION_CRITERIA = [
    # Top 20 desktop browser crashes on Release
    {
        "product": "Firefox",
        "channel": "release",
        "tc_limit": 20,
        "tc_startup_limit": 30,
    },
    # Top 20 desktop browser crashes on Beta
    {
        "product": "Firefox",
        "channel": "beta",
        "tc_limit": 20,
        "tc_startup_limit": 30,
    },
    # Top 10 desktop browser crashes on Nightly
    {
        "product": "Firefox",
        "channel": "nightly",
        "tc_limit": 10,
    },
    # Top 10 plugin crashes on Beta and Release
    {
        "product": "Firefox",
        "process_type": "plugin",
        "channel": ["beta", "release"],
        "tc_limit": 10,
    },
    # Top 5 desktop browser crashes on Linux-, Mac-, and Win8- specific list on
    # Beta and Release
    {
        "product": "Firefox",
        "platform": "Linux",
        "channel": ["beta", "release"],
        "tc_limit": 5,
    },
    {
        "product": "Firefox",
        "platform": "Mac OS X",
        "channel": ["beta", "release"],
        "tc_limit": 5,
    },
    {
        "product": "Firefox",
        "platform": "Linux",
        "channel": ["beta", "release"],
        "tc_limit": 5,
    },
]

CRASH_SIGNATURE_BLOCK_LIST = [
    "OOM | small",
]


class Topcrash:
    def __init__(
        self,
        minimum_crashes: Optional[int] = 5,
        signature_block_list: list = CRASH_SIGNATURE_BLOCK_LIST,
    ) -> None:
        """Constructor

        Args:
            minimum_crashes: the minimum number of crashes to consider a
                signature in the top crashes.
            signature_block_list: a list of crash signature to be ignored.
        """
        self.minimum_crashes = minimum_crashes
        self.signature_is_not_list = [
            f"!={signature}" for signature in signature_block_list
        ]

    def get_signatures(
        self,
        date: Union[str, datetime],
        duration: Optional[int] = 7,
    ) -> Dict[str, dict]:
        """Fetch the top crashes from socorro.

        Top crashes will be queried twice for each release channel, one that
        targets startup crashes and another that targets all crashes.

        Args:
            date: the final date
            duration: the number of days to retrieve the crash data

        Returns:
            A dictionary where the keys are crash signatures, and the values are
            dictionaries that contains details about a crash signature.
        """

        start_date = lmdutils.get_date(date, duration)
        end_date = lmdutils.get_date(date)
        date_range = socorro.SuperSearch.get_search_date(start_date, end_date)

        data = {}
        searches = [
            socorro.SuperSearch(
                params=self.__get_params_from_criteria(date_range, criteria),
                handler=self.__signatures_handler(criteria),
                handlerdata=data,
            )
            for criteria in TOP_CRASH_IDENTIFICATION_CRITERIA
        ]

        for search in searches:
            search.wait()

        return data

    def __get_params_from_criteria(self, date_range: list, criteria: dict):
        params = {
            "product": criteria["product"],
            "process_type": criteria.get("process_type"),
            "date": date_range,
            "platform": criteria.get("platform"),
            "release_channel": criteria["channel"],
            "signature": self.signature_is_not_list,
            "_aggs.signature": [
                "startup_crash",
            ],
            "_results_number": 0,
            "_facets_size": criteria.get("tc_startup_limit", criteria["tc_limit"]),
        }
        return params

    @staticmethod
    def __is_startup_crash(signature: dict):
        return any(
            startup["term"] == "T" for startup in signature["facets"]["startup_crash"]
        )

    def __signatures_handler(self, criteria: dict):
        def handler(search_resp: dict, data: dict):
            """
            Handle and merge crash signatures form different quires.

            Only startup crashes will be considered after exceeding `tc_limit`
            and up to `tc_startup_limit`.
            """
            signatures = search_resp["facets"]["signature"][: criteria["tc_limit"]]
            for signature in signatures:
                if signature["count"] < self.minimum_crashes:
                    return

                name = signature["term"]
                if name not in data:
                    data[name] = {
                        "is_startup": self.__is_startup_crash(signature),
                    }
                else:
                    data[name]["is_startup"] |= self.__is_startup_crash(signature)

            if "tc_startup_limit" not in criteria:
                return

            assert criteria["tc_startup_limit"] > criteria["tc_limit"]
            signatures = search_resp["facets"]["signature"][
                criteria["tc_limit"] : criteria["tc_startup_limit"]
            ]
            for signature in signatures:
                if not self.__is_startup_crash(signature):
                    continue

                name = signature["term"]
                if name not in data:
                    data[name] = {
                        "is_startup": True,
                    }
                else:
                    data[name]["is_startup"] = True

        return handler
