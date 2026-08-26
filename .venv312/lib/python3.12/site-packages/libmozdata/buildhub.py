# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os
import re
from collections import defaultdict
from distutils.version import LooseVersion

import requests

from . import config

SEARCH_URL = os.getenv("BUILDHUB_SEARCH_URL", "https://buildhub.moz.tools/api/search")


class BadBuildhubRequest(Exception):
    """Fancy way of saying '400 Bad request'"""


def fetch(search_url, json):
    response = requests.post(
        search_url,
        json=json,
        headers={"User-Agent": config.get("User-Agent", "name", required=True)},
    )
    if response.status_code == 400:
        raise BadBuildhubRequest(search_url)
    response.raise_for_status()
    return response.json()


class VeryLooseVersion(LooseVersion):
    """Like LooseVersion but more flexible on bad types."""

    def _cmp(self, other):
        if isinstance(other, str):
            other = VeryLooseVersion(other)

        try:
            if self.version == other.version:
                return 0
            if self.version < other.version:
                return -1
            if self.version > other.version:
                return 1
        except TypeError:
            # Compare them as strings. Happens, for example, when paring
            # [int, int, int] with [int, str, int]
            if str(self) < str(other):
                return -1
            if str(self) > str(other):
                return 1
            return 0


def get_distinct_versions(**kwargs):
    """Needs doc string"""
    field = "target.version"

    response = _get_aggregate_response(field, **kwargs)

    keys = [x["key"] for x in response["aggregations"]["myaggs"][field]["buckets"]]
    keys.sort(key=VeryLooseVersion, reverse=True)
    return keys


def get_distinct_buildids(**kwargs):
    """Needs doc string"""
    field = "build.id"

    response = _get_aggregate_response(field, **kwargs)
    seen = set()
    build_ids = []
    for doc in response["aggregations"]["myaggs"][field]["buckets"]:
        key = doc["key"]
        if key not in seen:
            build_ids.append(key)
            seen.add(key)
    return build_ids


def _get_aggregate_response(field, **kwargs):
    search_url = kwargs.pop("_search_url", SEARCH_URL)
    verbose = kwargs.pop("_verbose", False)
    size = kwargs.pop("_size", 1000)

    filter_ = defaultdict(dict)
    filters = []

    if "product" in kwargs:
        # To avoid the rist of someone search for `product="Firefox"` when
        # they should have done `product="firefox"`.
        product = kwargs["product"]
        assert isinstance(product, str), type(product)
        product = product.lower()
        filters.append({"source.product": product})

    if "channel" in kwargs:
        channel = kwargs["channel"]
        assert isinstance(channel, str), type(channel)
        channel = channel.lower()
        filters.append({"target.channel": channel})

    include = ".*"
    if "startswith" in kwargs:
        include = kwargs.pop("startswith")
        include = "{}.*".format(re.escape(include))

    if len(filters) > 1:
        filter_ = {"bool": {"must": [{"term": x} for x in filters]}}
    elif filters:
        filter_ = {"term": filters[0]}
    else:
        filter_ = {"match_all": {}}

    search = {
        "aggs": {
            "myaggs": {
                "filter": filter_ or {"match_all": {}},
                "aggs": {
                    field: {
                        "terms": {
                            "field": field,
                            "size": size,
                            "order": {"_term": "desc"},
                            "include": include,
                        }
                    },
                    # "target.version_count": {
                    #     "cardinality": {"field": "target.version"}
                    # },
                },
            }
        },
        "size": 0,
    }

    if verbose:
        print(json.dumps(search, indent=3))

    response = fetch(search_url, search)
    return response
