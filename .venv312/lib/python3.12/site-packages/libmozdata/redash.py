# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import functools
import re
from datetime import timedelta

import six

from . import config, utils
from .connection import Connection, Query


class Redash(Connection):
    """re:dash connection: https://sql.telemetry.mozilla.org"""

    RE_DASH_URL = config.get("Re:dash", "URL", "https://sql.telemetry.mozilla.org")
    API_URL = RE_DASH_URL + "/api/queries"
    TOKEN = config.get("Re:dash", "token", "")

    def __init__(self, queries):
        """Constructor

        Args:
            queries (List[Query]): queries to pass to re:dash
        """
        super(Redash, self).__init__(self.RE_DASH_URL, queries=queries)

    def get_header(self):
        header = super(Redash, self).get_header()
        header["Authorization"] = "Key %s" % self.get_apikey()
        return header

    @staticmethod
    def default_handler(query_id, json, data):
        """Default handler

        Args:
            query_id (str): query id
            json (dict): json
            data (dict): data
        """
        data[query_id] = json

    @staticmethod
    def __get_rows(channel, versions, rows):
        if channel == "beta":
            pat = re.compile(r"([0-9]+\.0)b[0-9]+")
            _versions = set()
            for v in versions:
                m = pat.match(v)
                if m:
                    _versions.add(m.group(1))
        else:
            _versions = set(versions)

        majors = set()
        pat_major = re.compile(r"([0-9]+)")
        for v in versions:
            m = pat_major.match(v)
            if m:
                majors.add(m.group(1))

        _rows = []
        for row in rows:
            if row["channel"] == channel:
                if "build_version" not in row:
                    continue

                v = row["build_version"]

                if not v:
                    continue

                if v in _versions:
                    _rows.append(row)
                elif majors:
                    m = pat_major.match(v)
                    if m and m.group(1) in majors:
                        _rows.append(row)

        return _rows

    @staticmethod
    def get(query_ids):
        """Get queries results in json format

        Args:
            query_ids (List[str]): query id

        Returns:
            dict: containing result in json for each query
        """
        data = {}
        if isinstance(query_ids, six.string_types):
            url = Redash.API_URL + "/" + query_ids + "/results.json"
            Redash(
                Query(
                    url,
                    None,
                    functools.partial(Redash.default_handler, query_ids),
                    data,
                )
            ).wait()
        else:
            queries = []
            url = Redash.API_URL + "/%s/results.json"
            for query_id in query_ids:
                queries.append(
                    Query(
                        url % query_id,
                        None,
                        functools.partial(Redash.default_handler, query_id),
                        data,
                    )
                )
            Redash(queries=queries).wait()

        return data

    @staticmethod
    def get_khours(start_date, end_date, channel, versions, product):
        """Get the results for query 346, 387: https://sql.telemetry.mozilla.org/queries/346
                                               https://sql.telemetry.mozilla.org/queries/387
        Args:
            start_date (datetime.datetime): start date
            end_date (datetime.datetime): end date
            channel (str): the channel
            versions (List[str]): the versions
            product (str): the product

        Returns:
            dict: containing result in json for each query
        """
        qid = "387" if product == "FennecAndroid" else "346"

        khours = Redash.get(qid)
        rows = khours[qid]["query_result"]["data"]["rows"]
        res = {}

        start_date = utils.get_date_ymd(start_date)
        end_date = utils.get_date_ymd(end_date)

        # init the data
        duration = (end_date - start_date).days
        for i in range(duration + 1):
            res[start_date + timedelta(i)] = 0.0

        rows = Redash.__get_rows(channel, versions, rows)

        for row in rows:
            d = utils.get_date_ymd(row["activity_date"])
            if start_date <= d <= end_date:
                res[d] += row["usage_khours"]

        return res

    @staticmethod
    def get_number_of_crash(start_date, end_date, channel, versions, product):
        """Get the results for query 399, 400: https://sql.telemetry.mozilla.org/queries/399
                                               https://sql.telemetry.mozilla.org/queries/400
        Args:
            start_date (datetime.datetime): start date
            end_date (datetime.datetime): end date
            channel (str): the channel
            versions (List[str]): the versions
            product (str): the product

        Returns:
            dict: containing result in json for each query
        """
        qid = "400" if product == "FennecAndroid" else "399"

        crashes = Redash.get(qid)
        rows = crashes[qid]["query_result"]["data"]["rows"]
        res = {}
        stats = {"m+c": 0.0, "main": 0.0, "content": 0.0, "plugin": 0.0, "all": 0.0}

        start_date = utils.get_date_ymd(start_date)
        end_date = utils.get_date_ymd(end_date)

        # init the data
        duration = (end_date - start_date).days
        for i in range(duration + 1):
            res[start_date + timedelta(i)] = stats.copy()

        rows = Redash.__get_rows(channel, versions, rows)

        for row in rows:
            d = utils.get_date_ymd(row["date"])
            if d >= start_date and d <= end_date:
                stats = res[d]
                stats["m+c"] += row["main"] + row["content"]
                stats["main"] += row["main"]
                stats["content"] += row["content"]
                stats["plugin"] += row["plugin"] + row["gmplugin"]
                stats["all"] += row["total"]

        return res
