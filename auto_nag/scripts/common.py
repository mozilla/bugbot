# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bugzilla.utils import get_config_path
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
import json


def get_login_info():
    with open(get_config_path(), 'r') as In:
        return json.load(In)


def send_email(category="UNDEFINED", date='today', dryrun=False, template='', title=''):
    login_info = get_login_info()
    if title:
        mail.send(login_info['ldap_username'],
                  utils.get_config('no_assignee', 'receivers', ['sylvestre@mozilla.com']),
                  title, body,
                  html=True, login=login_info, dryrun=dryrun)
    else:
        print('{}: No data for {}'.format(category, date))
