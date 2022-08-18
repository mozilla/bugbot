# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# This file was originally copied from https://github.com/mozilla/libmozdata/blob/v0.1.82/tests/auto_mock.py

import gzip
import hashlib
import os
import pickle
import re
import unittest
from typing import List
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlparse
from urllib.request import Request, urlopen

import responses

from auto_nag import logger

MOCKS_DIR = os.path.join(os.path.dirname(__file__), "tests/mocks")


class MockTestCase(unittest.TestCase):
    """
    Mock responses from any webserver (through requests)
    Register local responses when none are found
    """

    mock_urls: List[str] = []

    def setUp(self):

        # Setup mock callbacks
        for mock_url in self.mock_urls:
            url_re = re.compile(rf"^{mock_url}")
            responses.add_callback(
                responses.GET,
                url_re,
                callback=self._request_callback,
                content_type="application/json",
            )

    def _request_callback(self, request):
        logger.debug("Mock request %s %s", request.method, request.url)
        path = self._build_path(request.method, request.url)

        if os.path.exists(path):
            # Load local file
            logger.info("Using mock file %s", path)
            with gzip.open(path, "rb") as file:
                response = pickle.load(file)
        else:
            # Build from actual request
            logger.info("Building mock file %s", path)
            response = self._real_request(request)

            # Save in local file for future use
            with gzip.open(path, "wb") as file:
                # Use old pickle ascii protocol (default)
                # to be compatible with Python 2
                file.write(pickle.dumps(response, protocol=2))

        return (response["status"], response["headers"], response["body"])

    def _build_path(self, method, url):
        """
        Build a unique filename from method & url
        """
        # Build directory to request
        out = urlparse(url)
        parts = [f"{out.scheme}_{out.hostname}"]
        parts += filter(None, out.path.split("/"))
        directory = os.path.join(MOCKS_DIR, *parts)

        # Build sorted query filename
        query = sorted(parse_qsl(out.query))
        query = [f"""{k}={v.replace("/", "_")}""" for k, v in query]
        query_str = "_".join(query)

        # Use hashes to avoid too long names
        if len(query_str) > 150:
            hashed_query = hashlib.md5(query_str.encode("utf-8")).hexdigest()
            query_str = f"{query_str[0:100]}_{hashed_query}"
        filename = f"{method}_{query_str}.gz"

        # Build directory
        if not os.path.isdir(directory):
            try:
                os.makedirs(directory)
            except Exception as error:
                logger.error("Concurrency error when building directories: %s", error)

        return os.path.join(directory, filename)

    def _real_request(self, request):
        """
        Do a real request towards the target
        to build a mockup, using low level urllib
        Can't use requests: it's wrapped by unittest.mock
        """

        # No gzip !
        headers = {key.lower(): value for key, value in request.headers.items()}
        if "accept-encoding" in headers:
            del headers["accept-encoding"]

        real_req = Request(
            request.url, request.body, headers=headers, method=request.method
        )

        try:
            resp = urlopen(real_req)
        except HTTPError as error:
            logger.error("HTTP Error saved for %s: %s", request.url, error)
            return {"status": error.code, "headers": {}, "body": ""}

        return {
            "status": resp.code,
            # TODO: fix cookie usage bug
            # 'headers': dict(resp.getheaders()),
            "headers": {},
            "body": resp.read().decode("utf-8"),
        }
