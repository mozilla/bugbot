# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from libmozdata.utils import batched

from . import config
from .connection import Connection, Query


class CrashClouseau(Connection):
    URL = config.get("Clouseau", "URL", "https://clouseau.moz.tools")
    API_URL = URL + "/api"


class Reports(CrashClouseau):
    API_URL = CrashClouseau.API_URL + "/reports"

    def __init__(
        self, params=None, handler=None, handlerdata=None, queries=None, **kwargs
    ):
        """Constructor

        Args:
            params (Optional[dict]): the params for the query
            handler (Optional[function]): handler to use with the result of the query
            handlerdata (Optional): data used in second argument of the handler
            queries (Optional[List[Query]]): queries to execute
        """
        if queries is not None:
            super().__init__(self.URL, queries, **kwargs)
        else:
            super().__init__(
                self.URL, Query(self.API_URL, params, handler, handlerdata), **kwargs
            )

    @staticmethod
    def _default_handler(res, data):
        for report in res:
            signature = report["signature"]
            if signature not in data:
                data[signature] = [report]
            else:
                data[signature].append(report)

    @classmethod
    def get_by_signatures(cls, signatures, product=None, channel=None):
        """Get reports by signatures

        Args:
            signatures: signatures to get their reports.
            product: filter out reports that are not from this product.
            channel: filter out reports that are not from this release channel.

        Returns:
            dict: the reports by signatures
        """
        data = {}
        requests = [
            cls(
                params={
                    "signatures": signatures_batch,
                    "product": product,
                    "channel": channel,
                },
                handler=cls._default_handler,
                handlerdata=data,
            )
            for signatures_batch in batched(signatures, 20)
        ]

        for request in requests:
            request.wait()

        return data
