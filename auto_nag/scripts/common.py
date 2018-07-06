# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bugzilla.utils import get_config_path
import json

def get_login_info():
    with open(get_config_path(), 'r') as In:
        return json.load(In)
