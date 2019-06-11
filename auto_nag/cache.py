# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os

from libmozdata import utils as lmdutils

from auto_nag import utils


class Cache(object):
    def __init__(self, name, max_days, add_once=True):
        super(Cache, self).__init__()
        self.name = name
        self.max_days = max_days
        self.add_once = add_once
        self.added = False
        self.dryrun = True
        self.data = None

    def set_dry_run(self, dryrun):
        self.dryrun = dryrun or self.max_days < 1

    def get_path(self):
        cache_path = utils.get_config("common", "cache")
        if not os.path.exists(cache_path):
            os.mkdir(cache_path)
        return "{}/{}.json".format(cache_path, self.name)

    def get_data(self):
        if self.data is None:
            path = self.get_path()
            self.data = {}
            if os.path.exists(path):
                with open(path, "r") as In:
                    data = json.load(In)
                    for bugid, date in data.items():
                        delta = lmdutils.get_date_ymd("today") - lmdutils.get_date_ymd(
                            date
                        )
                        if delta.days < self.max_days:
                            self.data[int(bugid)] = date
        return self.data

    def add(self, bugids):
        if self.dryrun or (self.add_once and self.added):
            return

        data = self.get_data()
        today = lmdutils.get_today()
        for bugid in bugids:
            data[int(bugid)] = today

        with open(self.get_path(), "w") as Out:
            json.dump(data, Out)

        self.added = True

    def __contains__(self, key):
        return not self.dryrun and int(key) in self.get_data()
