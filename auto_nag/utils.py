# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
from libmozdata import release_calendar as rc
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
_TRIAGE_OWNERS = None
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
    tool_conf = conf[name]
    if entry in tool_conf:
        return tool_conf[entry]
    tool_conf = conf['common']
    return tool_conf.get(entry, default)


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


def get_empty_assignees(params):
    n = get_last_field_num(params)
    n = int(n)
    params.update(
        {
            'j' + str(n): 'OR',
            'f' + str(n): 'OP',
            'f' + str(n + 1): 'assigned_to',
            'o' + str(n + 1): 'equals',
            'v' + str(n + 1): 'nobody@mozilla.org',
            'f' + str(n + 2): 'assigned_to',
            'o' + str(n + 2): 'regexp',
            'v' + str(n + 2): r'^.*\.bugs$',
            'f' + str(n + 3): 'assigned_to',
            'o' + str(n + 3): 'isempty',
            'f' + str(n + 4): 'CP',
        }
    )
    return params


def is_no_assignee(mail):
    return mail == 'nobody@mozilla.org' or mail.endswith('.bugs') or mail == ''


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
    return rc.get_next_release_date()


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

    x = max(s) + 1 if s else 1
    return str(x)


def get_bz_search_url(params):
    return 'https://bugzilla.mozilla.org/buglist.cgi?' + urlencode(params, doseq=True)


def has_bot_set_ni(bug):
    bot = get_config('common', 'bot_bz_mail')
    for flag in get_needinfo(bug):
        if flag['setter'] in bot:
            return True
    return False


def get_triage_owners():
    global _TRIAGE_OWNERS
    if _TRIAGE_OWNERS is not None:
        return _TRIAGE_OWNERS

    # accessible is the union of:
    #  selectable (all product we can see)
    #  enterable (all product a user can file bugs into).
    prods = get_config('common', 'products')
    url = 'https://bugzilla.mozilla.org/rest/product'
    params = {
        'type': 'accessible',
        'include_fields': ['components.name', 'components.triage_owner'],
        'names': prods,
    }
    r = requests.get(url, params=params)
    products = r.json()['products']
    _TRIAGE_OWNERS = {}
    for prod in products:
        for comp in prod['components']:
            owner = comp['triage_owner']
            if owner and not is_no_assignee(owner):
                comp_name = comp['name']
                if owner not in _TRIAGE_OWNERS:
                    _TRIAGE_OWNERS[owner] = [comp_name]
                else:
                    _TRIAGE_OWNERS[owner].append(comp_name)
    return _TRIAGE_OWNERS


def organize(bugs, columns):
    if isinstance(bugs, dict):
        # we suppose that the values are the bugdata dict
        bugs = bugs.values()

    def identity(x):
        return x

    def bugid_key(x):
        return -int(x)

    lambdas = {'id': bugid_key}

    def mykey(p):
        return tuple(lambdas.get(c, identity)(x) for x, c in zip(p, columns))

    if len(columns) >= 2:
        res = [tuple(info[c] for c in columns) for info in bugs]
    else:
        c = columns[0]
        res = [info[c] for info in bugs]

    return sorted(res, key=mykey)
