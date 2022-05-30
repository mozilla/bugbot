# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime
from typing import Dict, Optional, Union

import libmozdata.socorro as socorro
from libmozdata import utils as lmdutils


class Topcrash:
    def __init__(
        self,
        minimum_crashes: Optional[int] = 0,
        minimum_startup_crashes: Optional[int] = 0,
    ) -> None:
        """Constructor

        Args:
            minimum_crashes: the minimum number of crashes to consider a
                signature in the top crashes.
            minimum_startup_crashes: the minimum number of crashes to consider a
                signature as a startup crash.
        """
        self.minimum_crashes = minimum_crashes
        self.minimum_startup_crashes = minimum_startup_crashes

    def get_signatures(
        self,
        date: Union[str, datetime],
        duration: Optional[int] = 11,
        tc_limit: Optional[int] = 50,
    ) -> Dict[str, bool]:
        """Fetch the top crashes from socorro.

        Top crashes will be queried twice for each release channel, one that
        targets startup crashes and another that targets all crashes.

        Args:
            date: the final date
            duration: the number of days to retrieve the crash data
            tc_limit: the number of topcrashes to load on each query

        Returns:
            A dictionary where the keys are crash signatures, and the values are
            booleans that indicate whether a crash is a startup crash or not.
        """

        start_date = lmdutils.get_date(date, duration - 1)
        end_date = lmdutils.get_date(date)
        date_range = socorro.SuperSearch.get_search_date(start_date, end_date)

        params_combinations = [
            {
                "product": "Firefox",
                "date": date_range,
                "release_channel": channel,
                "startup_crash": is_startup,
                "_aggs.signature": [
                    "startup_crash",
                ],
                "_results_number": 0,
                "_facets_size": tc_limit,
            }
            for channel in ("release", "beta", "nightly")
            for is_startup in (True, None)
        ]
        data = {}

        searches = [
            socorro.SuperSearch(
                params=params,
                handler=self.__startup_signatures_handler,
                handlerdata=data,
            )
            for params in params_combinations
        ]

        for search in searches:
            search.wait()

        return data

    def __startup_signatures_handler(self, search_resp: dict, data: dict):
        for signature in search_resp["facets"]["signature"]:
            if signature["count"] < self.minimum_crashes:
                break

            is_startup = any(
                # Check if the signature has numbers for startup crashes
                startup["term"] == "T"
                and startup["count"] >= self.minimum_startup_crashes
                for startup in signature["facets"]["startup_crash"]
            )

            data[signature["term"]] = data.get(signature["term"], False) or is_startup
