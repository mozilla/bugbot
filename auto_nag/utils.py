# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json


_CONFIG = None


def _get_config():
    global _CONFIG
    if _CONFIG is None:
        with open('./auto_nag/scripts/configs/tools.json', 'r') as In:
            _CONFIG = json.load(In)
    return _CONFIG


def get_config(name, entry):
    conf = _get_config()
    return conf.get(name, {}).get(entry)
