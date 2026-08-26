# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import multiprocessing

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from requests_futures.sessions import FuturesSession

from . import config, utils


class Query(object):
    """To use with a Connection

    A query contains the params and the handler to use for these params.
    """

    def __init__(self, url, params=None, handler=None, handlerdata=None):
        """Constructor

        Args:
            url (str): the url
            params (Optional[dict]): the params
            handler (Optional[function]): the handler to apply to the json
            handlerdata (Optional): the data passed as second argument of handler
        """
        self.url = url
        self.params = params
        self.handler = handler
        self.handlerdata = handlerdata

    def params_repr(self, params):
        return utils.get_params_for_url(params)

    def __repr__(self):
        params_list = self.params

        if not isinstance(params_list, list):
            params_list = [self.params]

        return "\n".join(
            "url: %s" % self.url + self.params_repr(params) for params in params_list
        )


class Connection(object):
    """Represents a connection to a server"""

    VERIFY_SSL = True
    TIMEOUT = 30
    MAX_RETRIES = 256
    MAX_WORKERS = multiprocessing.cpu_count()
    RAISE_ERROR = True
    CHUNK_SIZE = 32
    TOKEN = ""
    USER_AGENT = None
    X_FORWARDED_FOR = utils.get_x_fwed_for_str(
        config.get("X-Forwarded-For", "data", "")
    )

    # Error 429 is for 'Too many requests' => we retry
    STATUS_FORCELIST = [429]

    def __init__(self, base_url, queries=None, **kwargs):
        """Constructor

        Args:
            base_url (str): the server's url
            queries (Optional[Query]): the queries
        """

        self.session = FuturesSession(max_workers=self.MAX_WORKERS)
        retries = Retry(
            total=Connection.MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=Connection.STATUS_FORCELIST,
        )
        self.session.mount(base_url, HTTPAdapter(max_retries=retries))
        self.results = []
        self.queries = queries

        if kwargs:
            if "timeout" in kwargs:
                self.TIMEOUT = kwargs["timeout"]
            if "max_retries" in kwargs:
                self.MAX_RETRIES = kwargs["max_retries"]
            if "max_workers" in kwargs:
                self.MAX_WORKERS = kwargs["max_workers"]
            if "user_agent" in kwargs:
                self.USER_AGENT = kwargs["user_agent"]
            if "x_forwarded_for" in kwargs:
                self.X_FORWARDED_FOR = utils.get_x_fwded_for_str(
                    kwargs["x_forwarded_for"]
                )
            if "raise_error" in kwargs:
                self.RAISE_ERROR = kwargs["raise_error"]

        if not self.USER_AGENT:
            self.USER_AGENT = config.get("User-Agent", "name", required=True)

        self.exec_queries()

    def __get_cb(self, query):
        """Get the callback to use when data have been retrieved

        Args:
            query (Query): the query

        Returns:
            function: the callback for the query
        """

        def cb(res, *args, **kwargs):
            if res.status_code == 200:
                try:
                    response = res.json()
                except ValueError:
                    response = res.text

                if query.handlerdata is not None:
                    query.handler(response, query.handlerdata)
                else:
                    query.handler(response)
            elif self.RAISE_ERROR:
                res.raise_for_status()
            else:
                print("Connection error:")
                print("   url: ", res.url)
                print("   text: ", res.text)

        return cb

    def wait(self):
        """Just wait that all the queries have been treated"""
        for r in self.results:
            r.result()

    def get_apikey(self):
        """Get the api key

        Returns:
            str: the api key
        """
        return self.TOKEN

    def get_header(self):
        """Get the header to use each query

        Returns:
            dict: the header
        """
        if self.X_FORWARDED_FOR:
            return {
                "User-Agent": self.USER_AGENT,
                "X-Forwarded-For": self.X_FORWARDED_FOR,
                "Connection": "close",
            }
        else:
            return {"User-Agent": self.USER_AGENT, "Connection": "close"}

    def get_auth(self):
        """Get the auth to use each query

        Returns:
            dict: the auth
        """
        return None

    def exec_queries(self, queries=None):
        """Set and exec some queries

        Args:
            queries (Optional[Query]): the queries to exec
        """
        if queries:
            self.queries = queries

        if self.queries:
            if isinstance(self.queries, Query):
                self.queries = [self.queries]

            header = self.get_header()
            auth = self.get_auth()

            for query in self.queries:
                cb = self.__get_cb(query)
                if query.params:
                    if isinstance(query.params, dict):
                        self.results.append(
                            self.session.get(
                                query.url,
                                params=query.params,
                                headers=header,
                                auth=auth,
                                verify=self.VERIFY_SSL,
                                timeout=self.TIMEOUT,
                                hooks={"response": cb},
                            )
                        )
                    else:
                        for p in query.params:
                            self.results.append(
                                self.session.get(
                                    query.url,
                                    params=p,
                                    headers=header,
                                    auth=auth,
                                    verify=self.VERIFY_SSL,
                                    timeout=self.TIMEOUT,
                                    hooks={"response": cb},
                                )
                            )
                else:
                    self.results.append(
                        self.session.get(
                            query.url,
                            headers=header,
                            auth=auth,
                            verify=self.VERIFY_SSL,
                            timeout=self.TIMEOUT,
                            hooks={"response": cb},
                        )
                    )

    @staticmethod
    def chunks(data, chunk_size=CHUNK_SIZE):
        """Get chunk from a list

        Args:
            data (List): data to chunkify
            chunk_size (Optional[int]): the size of each chunk

        Yields:
            a chunk from the data
        """
        for i in range(0, len(data), chunk_size):
            yield data[i : (i + chunk_size)]
