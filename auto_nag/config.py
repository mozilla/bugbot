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
            self.conf = {"bz_api_key": ""}
        else:
            with open(MyConfig.PATH) as In:
                self.conf = json.load(In)
                if not self.conf.get("bz_api_key", None):
                    raise Exception(
                        "Your config.json file must contain a Bugzilla token"
                    )

    def get(self, section, option, default=None, type=str):
        if section == "Bugzilla":
            if option == "token":
                return self.conf["bz_api_key"]
        elif section == "User-Agent":
            return "relman-auto-nag"
        return default


config.set_config(MyConfig())
