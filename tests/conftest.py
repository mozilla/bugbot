# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os

import pytest

from bugbot.auto_mock import MockTestCase


@pytest.fixture
def setup_mock_urls():
    """Register mock URL callbacks using the MockTestCase logic.

    Returns a callable that takes a list of base URLs. Tests that hit the
    network should still be decorated with ``@responses.activate``.
    """

    def _setup(urls):
        mc = MockTestCase()
        mc.mock_urls = urls
        mc.setUp()

    return _setup


@pytest.fixture(scope="session")
def bmo():
    """The database of the local BMO the scenarios run against, started if
    needed (see tests/framework/bmo.py).

    The tests using it are skipped if BMO can't be started (e.g. without
    Docker), unless BUGBOT_REQUIRE_BMO is set.
    """
    from tests.framework import bmo

    try:
        return bmo.ensure_running()
    except bmo.BMOUnavailable as e:
        if os.environ.get("BUGBOT_REQUIRE_BMO"):
            raise
        pytest.skip(f"No local BMO: {e}")
