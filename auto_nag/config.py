# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os

from libmozdata import config


class MyConfig(config.Config):

    PATH = "auto_nag/scripts/configs/config.json"

    def __init__(self):
        super(MyConfig, self).__init__()
        if not os.path.exists(MyConfig.PATH):
            self.conf = {"bz_api_key": "", "bz_api_key_nomail": ""}
        else:
            with open(MyConfig.PATH) as In:
                self.conf = json.load(In)

        if "bz_api_key" not in self.conf:
            raise Exception("Your config.json file must contain a Bugzilla token")

        if "bz_api_key_nomail" not in self.conf:
            raise Exception(
                "Your config.json file must contain a Bugzilla token for account that doesn't trigger bugmail"
            )

    def get(self, section, option, default=None, type=str):
        if section == "Bugzilla":
            if option == "token":
                return self.conf["bz_api_key"]
            if option == "nomail-token":
                return self.conf["bz_api_key_nomail"]
        elif section == "User-Agent":
            return "relman-auto-nag"
        return default


def load():
    config.set_config(MyConfig())
