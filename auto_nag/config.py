# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import config
import json


class MyConfig(config.Config):
    def __init__(self):
        super(MyConfig, self).__init__()
        with open('auto_nag/scripts/configs/config.json') as In:
            self.conf = json.load(In)
            if not self.conf.get('bz_api_key', None):
                raise Exception('Your config.json file must contain a Bugzilla token')

    def get(self, section, option, default=None, type=str):
        if section == 'Bugzilla':
            if option == 'token':
                return self.conf['bz_api_key']
        elif section == 'User-Agent':
            return 'relman-auto-nag'
        return default


config.set_config(MyConfig())
