# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from connection import Connection


class FXRevision(Connection):
    ARCHIVES_URL = "http://archive.mozilla.org"
    NIGHTLY_URL = ARCHIVES_URL + "/pub/firefox/nightly/"

    def __init__(self, versions, fx_version, os):
        super(FXRevision, self).__init__(self.ARCHIVES_URL)
        self.dates = {}
        self.fx_version = fx_version
        self.os = os
        self.info = {}
        pattern = re.compile(
            "([0-9]{4})([0-9]{2})([0-9]{2})([0-9]{2})([0-9]{2})([0-9]{2})"
        )
        for version in versions:
            m = pattern.search(version)
            self.dates[version] = [m.group(i) for i in range(1, 7)]

        self.__get_info()

    def get(self):
        self.wait()
        return self.info

    def __make_url(self, date):
        return "%s%s/%s/%s-mozilla-central/firefox-%s.en-US.%s.json" % (
            self.NIGHTLY_URL,
            date[0],
            date[1],
            "-".join(date),
            self.fx_version,
            self.os,
        )

    def __info_cb(self, res, *args, **kwargs):
        json = res.json()
        self.info[json["buildid"]] = json["moz_source_stamp"]

    def __get_info(self):
        for date in self.dates.values():
            self.results.append(
                self.session.get(
                    self.__make_url(date),
                    timeout=self.TIMEOUT,
                    hooks={"response": self.__info_cb},
                )
            )


# fxr = FXRevision(['20160223030304'], '47.0a1', 'linux-i686')
# pprint(fxr.get())

#    2016/02/2016-02-23-03-03-04-mozilla-central/firefox-47.0a1.en-US.linux-i686.txt'
