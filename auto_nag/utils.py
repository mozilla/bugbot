# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import dateutil.parser
import json
import re
import requests
import six

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

from auto_nag.bugzilla.utils import get_config_path


_CONFIG = None
_CYCLE_SPAN = None
_NEXT_RELEASE = None
TEMPLATE_PAT = re.compile(r'<p>(.*)</p>', re.DOTALL)
BZ_FIELD_PAT = re.compile(r'^[fovj]([0-9]+)$')


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


def get_signatures(sgns):
    res = set()
    sgns = map(lambda x: x.strip(), sgns.split('[@'))
    for s in filter(None, sgns):
        try:
            i = s.rindex(']')
            res.add(s[:i].strip())
        except ValueError:
            res.add(s)
    return res


def get_login_info():
    with open(get_config_path(), 'r') as In:
        return json.load(In)


def plural(sword, data, pword=''):
    if isinstance(data, six.integer_types):
        p = data != 1
    else:
        p = len(data) != 1
    if not p:
        return sword
    if pword:
        return pword
    return sword + 's'


def get_cycle_span():
    global _CYCLE_SPAN
    if _CYCLE_SPAN is None:
        url = 'https://wiki.mozilla.org/Template:CURRENT_CYCLE'
        template_page = str(requests.get(url).text.encode('utf-8'))
        m = TEMPLATE_PAT.search(template_page)
        _CYCLE_SPAN = m.group(1).strip()
    return _CYCLE_SPAN


def get_next_release_date():
    global _NEXT_RELEASE
    if _NEXT_RELEASE is None:
        url = 'https://wiki.mozilla.org/Template:NextReleaseDate'
        template_page = str(requests.get(url).text.encode('utf-8'))
        m = TEMPLATE_PAT.search(template_page)
        _NEXT_RELEASE = dateutil.parser.parse(m.group(1).strip())
    return _NEXT_RELEASE


def get_report_bugs(channel):
    url = 'https://bugzilla.mozilla.org/page.cgi?id=release_tracking_report.html'
    params = {'q': 'approval-mozilla-{}:+:{}:0:and:'.format(channel, get_cycle_span())}

    # allow_redirects=False avoids to load the data
    # and we'll just get the redirected url to get all the bug ids we need
    r = requests.get(url, params=params, allow_redirects=False)

    # something like https://bugzilla.mozilla.org/buglist.cgi?bug_id=1493711,1502766,1499908
    url = r.headers['Location']

    return url.split(',')[1:]


def get_flag(version, name, channel):
    if name in ['status', 'tracking']:
        if channel == 'esr':
            return 'cf_{}_firefox_esr{}'.format(name, version)
        return 'cf_{}_firefox{}'.format(name, version)
    elif name == 'approval':
        if channel == 'esr':
            return 'approval-mozilla-esr{}'.format(version)
        return 'approval-mozilla-{}'.format(channel)


def get_needinfo(bug):
    for flag in bug.get('flags', []):
        if flag.get('name', '') == 'needinfo' and flag['status'] == '?':
            yield flag


def get_last_field_num(params):
    s = set()
    for k in params.keys():
        m = BZ_FIELD_PAT.match(k)
        if m:
            s.add(int(m.group(1)))

    return max(s) + 1 if s else 1


def get_bz_search_url(params):
    return 'https://bugzilla.mozilla.org/buglist.cgi?' + urlencode(params, doseq=True)
