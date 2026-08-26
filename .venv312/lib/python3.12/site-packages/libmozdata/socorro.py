# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import six

from . import config, utils
from .connection import Connection, Query


class Socorro(Connection):
    """Socorro connection: https://crash-stats.mozilla.org"""

    CRASH_STATS_URL = config.get("Socorro", "URL", "https://crash-stats.mozilla.org")
    API_URL = CRASH_STATS_URL + "/api"
    TOKEN = config.get("Socorro", "token", "")

    def __init__(self, queries, **kwargs):
        """Constructor

        Args:
            queries (List[Query]): queries to pass to Socorro
        """
        super(Socorro, self).__init__(self.CRASH_STATS_URL, queries=queries, **kwargs)

    def get_header(self):
        header = super(Socorro, self).get_header()
        header["Auth-Token"] = self.get_apikey()
        return header


class SuperSearch(Socorro):
    """SuperSearch: https://crash-stats.mozilla.org/api/#SuperSearch"""

    URL = Socorro.API_URL + "/SuperSearch/"
    WEB_URL = Socorro.CRASH_STATS_URL + "/search/"

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
            super(SuperSearch, self).__init__(queries, **kwargs)
        else:
            if self.__has_deprecated_unredacted_params(params):
                raise ValueError(
                    "Requesting PII data using the `SuperSearch` class is not "
                    "supported anymore. Please use `SuperSearchUnredacted` instead."
                )
            super(SuperSearch, self).__init__(
                Query(self.URL, params, handler, handlerdata), **kwargs
            )

    def __has_deprecated_unredacted_params(self, params):
        """Check if the params is requesting PII data that we used to
        automatically support retrieving it by redirecting the request to the
        unredacted endpoint (i.e., SuperSearchUnredacted).
        """
        if not isinstance(params, dict):
            # This is a workaround to avoid crashing when the params values is a
            # list of params. We could instead of this, check each item in the
            # list, but it's not worth it since this method is just for backward
            # compatibility.
            return False

        unredacted = False
        if "_facets" in params:
            facets = params["_facets"]
            if "url" in facets or "email" in facets:
                unredacted = True
        if not unredacted and "_columns" in params:
            columns = params["_columns"]
            if "url" in columns or "email" in columns:
                unredacted = True
        if not unredacted:
            for k, v in params.items():
                if (
                    "url" in k
                    or "email" in k
                    or (
                        (isinstance(v, list) or isinstance(v, six.string_types))
                        and ("url" in v or "email" in v)
                    )
                ):
                    unredacted = True
        return unredacted

    @staticmethod
    def get_link(params):
        return utils.get_url(SuperSearch.WEB_URL) + utils.get_params_for_url(params)

    @staticmethod
    def get_search_date(start, end=None):
        """Get a search date list for [start, end[ (end can be in the future)

        Args:
            start (str): start date in 'YYYY-mm-dd' format or 'today'
            end (str): start date in 'YYYY-mm-dd' format or 'today'

        Returns:
            List(str): containing acceptable interval for Socorro.SuperSearch
        """
        _start = utils.get_date(start)

        if end:
            _end = utils.get_date_ymd(end)
            today = utils.get_date_ymd("today")
            if _end > today:
                search_date = [">=" + _start]
            else:
                search_date = [">=" + _start, "<" + utils.get_date_str(_end)]
        else:
            search_date = [">=" + _start]

        return search_date


class SuperSearchUnredacted(SuperSearch):
    """SuperSearchUnredacted: https://crash-stats.mozilla.org/api/#SuperSearchUnredacted"""

    URL = Socorro.API_URL + "/SuperSearchUnredacted/"


class ProcessedCrash(Socorro):
    """ProcessedCrash: https://crash-stats.mozilla.org/api/#ProcessedCrash"""

    URL = Socorro.API_URL + "/ProcessedCrash/"

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
        if queries:
            super(ProcessedCrash, self).__init__(queries, **kwargs)
        else:
            super(ProcessedCrash, self).__init__(
                Query(ProcessedCrash.URL, params, handler, handlerdata), **kwargs
            )

    @staticmethod
    def default_handler(json, data):
        """Default handler

        Args:
            json (dict): json
            data (dict): dictionary to update with data
        """
        data.update(json)

    @staticmethod
    def get_processed(crashids):
        """Get processed crashes

        Args:
            crashids (Optional[list[str]]): the crash ids

        Returns:
            dict: the processed crashes
        """

        data = {}
        __base = {"crash_id": None, "datatype": "processed"}

        if isinstance(crashids, six.string_types):
            __base["crash_id"] = crashids
            _dict = {}
            data[crashids] = _dict
            ProcessedCrash(
                params=__base, handler=ProcessedCrash.default_handler, handlerdata=_dict
            ).wait()
        else:
            queries = []
            for crashid in crashids:
                cparams = __base.copy()
                cparams["crash_id"] = crashid
                _dict = {}
                data[crashid] = _dict
                queries.append(
                    Query(
                        ProcessedCrash.URL,
                        cparams,
                        ProcessedCrash.default_handler,
                        _dict,
                    )
                )
            ProcessedCrash(queries=queries).wait()

        return data


class Bugs(Socorro):
    """Bugs: https://crash-stats.mozilla.org/api/#Bugs"""

    URL = Socorro.API_URL + "/Bugs/"

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
        if queries:
            super(Bugs, self).__init__(queries, **kwargs)
        else:
            super(Bugs, self).__init__(
                Query(Bugs.URL, params, handler, handlerdata), **kwargs
            )

    @staticmethod
    def get_bugs(signatures):
        """Get signatures bugs

        Args:
            signatures (List[str]): the signatures

        Returns:
            dict: the bugs for each signature
        """

        def default_handler(json, data):
            if json["total"]:
                for hit in json["hits"]:
                    signature = hit["signature"]
                    if signature in data:
                        data[signature].add(hit["id"])

        if isinstance(signatures, six.string_types):
            data = {signatures: set()}
            Bugs(
                params={"signatures": signatures},
                handler=default_handler,
                handlerdata=data,
            ).wait()
        else:
            data = {s: set() for s in signatures}
            queries = []
            for sgns in Connection.chunks(signatures, 10):
                queries.append(
                    Query(Bugs.URL, {"signatures": sgns}, default_handler, data)
                )
            Bugs(queries=queries).wait()

        for k, v in data.items():
            data[k] = list(v)

        return data


class SignatureFirstDate(Socorro):
    """SignatureFirstDate: https://crash-stats.mozilla.org/api/#SignatureFirstDate"""

    URL = Socorro.API_URL + "/SignatureFirstDate/"

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
        if queries:
            super(SignatureFirstDate, self).__init__(queries, **kwargs)
        else:
            super(SignatureFirstDate, self).__init__(
                Query(SignatureFirstDate.URL, params, handler, handlerdata), **kwargs
            )

    @staticmethod
    def get_signatures(signatures):
        """Get the first date and build id for the specified signatures.

        Args:
            signatures (List[str]): signatures to check.

        Returns:
            dict: the first date for each signature.
        """

        def default_handler(json, data):
            data.extend(json["hits"])

        data = []
        SignatureFirstDate(
            params={"signatures": signatures},
            handler=default_handler,
            handlerdata=data,
        ).wait()

        return data
