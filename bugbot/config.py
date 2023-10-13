# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os

from libmozdata import config


class MyConfig(config.Config):
    PATH = "configs/config.json"

    def __init__(self):
        super(MyConfig, self).__init__()
        if not os.path.exists(MyConfig.PATH):
            self.conf = {"bz_api_key": "", "bz_api_key_nomail": "", "socorro_token": ""}
        else:
            with open(MyConfig.PATH) as In:
                self.conf = json.load(In)

        if "bz_api_key" not in self.conf:
            raise Exception("Your config.json file must contain a Bugzilla token")

        if "bz_api_key_nomail" not in self.conf:
            raise Exception(
                "Your config.json file must contain a Bugzilla token for an account that doesn't trigger bugmail (for testing, you can use the same token as bz_api_key)"
            )

        if "socorro_token" not in self.conf:
            raise Exception("Your config.json file must contain a Socorro token")

    def get(self, section, option, default=None, type=str):
        if section == "Bugzilla":
            if option == "token":
                return self.conf["bz_api_key"]
            if option == "nomail-token":
                return self.conf["bz_api_key_nomail"]
        elif section == "Socorro":
            if option == "token":
                return self.conf["socorro_token"]
        elif section == "User-Agent":
            return "bugbot"
        return default


def load():
    config.set_config(MyConfig())
