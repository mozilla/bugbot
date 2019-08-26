# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import unittest

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils

from auto_nag.cache import Cache


class TestCache(unittest.TestCase):
    def test_cache(self):
        cache = Cache("test_cache", 7)
        cache.set_dry_run(False)

        bugids = [123, 456, 789]
        cache.add(bugids)

        for bugid in bugids:
            assert bugid in cache
            assert str(bugid) in cache

        assert 101112 not in cache
        assert "101112" not in cache

        with open(cache.get_path(), "r") as In:
            data = json.load(In)

        for bugid in ["123", "456"]:
            date = data[bugid]
            date = lmdutils.get_date_ymd(date) - relativedelta(days=8)
            data[bugid] = lmdutils.get_date_str(date)

        with open(cache.get_path(), "w") as Out:
            json.dump(data, Out)

        cache = Cache("test_cache", 7)
        cache.set_dry_run(False)

        assert 123 not in cache
        assert 456 not in cache
        assert 789 in cache
