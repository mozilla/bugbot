# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import requests


def get_bugbug_version(requirements):
    for line in requirements.splitlines():
        if line.startswith('bugbug=='):
            return line[len('bugbug=='):]

    return None


with open('requirements.txt') as f:
    autonag_bugbug_version = get_bugbug_version(f.read())

r = requests.get('https://raw.githubusercontent.com/mozilla/release-services/master/src/bugbug/train/requirements.txt')
train_bugbug_version = get_bugbug_version(r.text)

assert autonag_bugbug_version == train_bugbug_version, '{} should be {}'.format(autonag_bugbug_version, train_bugbug_version)
