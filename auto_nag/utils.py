# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import re


_CONFIG = None


def _get_config():
    global _CONFIG
    if _CONFIG is None:
        try:
            with open('./auto_nag/scripts/configs/tools.json', 'r') as In:
                data = In.read()
                pat = re.compile(r'^[ \t]*//.*$', re.MULTILINE)
                data = pat.sub('', data)
                _CONFIG = json.loads(data)
        except IOError:
            _CONFIG = {}
    return _CONFIG


def get_config(name, entry, default=None):
    conf = _get_config()
    if name not in conf:
        name = 'common'
    return conf.get(name, {}).get(entry, default)
