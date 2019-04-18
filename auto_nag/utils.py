# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import datetime
import dateutil.parser
from dateutil.relativedelta import relativedelta
import json
from libmozdata import utils as lmdutils
from libmozdata import release_calendar as rc
from libmozdata.hgmozilla import Mercurial
import os
import pytz
import re
import requests
import six

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

from auto_nag.bugzilla.utils import get_config_path
from auto_nag.common import get_current_versions


_CONFIG = None
_CYCLE_SPAN = None
_TRIAGE_OWNERS = None
_DEFAULT_ASSIGNEES = None

BZ_FIELD_PAT = re.compile(r'^[fovj]([0-9]+)$')
PAR_PAT = re.compile(r'\([^\)]*\)')
BRA_PAT = re.compile(r'\[[^\]]*\]')
DIA_PAT = re.compile('<[^>]*>')
UTC_PAT = re.compile(r'UTC\+[^ \t]*')
COL_PAT = re.compile(':[^:]*')
BACKOUT_PAT = re.compile('^back(s|(ed))?[ \t]*out', re.I)
BUG_PAT = re.compile(r'^bug[s]?[ \t]*([0-9]+)', re.I)


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
    if not sgns:
        return set()

    res = set()
    sgns = map(lambda x: x.strip(), sgns.split('[@'))
    for s in filter(None, sgns):
        try:
            i = s.rindex(']')
            res.add(s[:i].strip())
        except ValueError:
            res.add(s)
    return res


def add_signatures(old, new):
    added_sgns = '[@ ' + ']\n[@ '.join(sorted(new)) + ']'
    if old:
        return old + '\n' + added_sgns
    return added_sgns


def get_empty_assignees(params, negation=False):
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
    if negation:
        params['n' + str(n)] = 1

    return params


def is_no_assignee(mail):
    return mail == 'nobody@mozilla.org' or mail.endswith('.bugs') or mail == ''


def get_login_info():
    with open(get_config_path(), 'r') as In:
        return json.load(In)


def get_private():
    with open(get_config_path(), 'r') as In:
        return json.load(In)['private']


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


def search_prev_merge(beta):
    tables = rc.get_all()

    # the first table is the future and the second is the recent past
    table = tables[1]
    central = table[0].index('Central')
    central = rc.get_versions(table[1][central])[0][0]

    # just check consistency
    assert beta == central

    merge = table[0].index('Merge Date')

    return lmdutils.get_date_ymd(table[1][merge])


def get_cycle_span():
    global _CYCLE_SPAN
    if _CYCLE_SPAN is None:
        cal = get_release_calendar()
        now = lmdutils.get_date_ymd('today')
        cycle = None
        for i, c in enumerate(cal):
            if now < c['merge']:
                if i == 0:
                    cycle = [search_prev_merge(c['beta']), c['merge']]
                else:
                    cycle = [cal[i - 1]['merge'], c['merge']]
                break
        if cycle:
            _CYCLE_SPAN = '-'.join(x.strftime('%Y%m%d') for x in cycle)

    return _CYCLE_SPAN


def get_next_release_date():
    return rc.get_next_release_date()


def get_release_calendar():
    return rc.get_calendar()


def get_report_bugs(channel, op='+'):
    url = 'https://bugzilla.mozilla.org/page.cgi?id=release_tracking_report.html'
    params = {
        'q': 'approval-mozilla-{}:{}:{}:0:and:'.format(channel, op, get_cycle_span())
    }

    # allow_redirects=False avoids to load the data
    # and we'll just get the redirected url to get all the bug ids we need
    r = requests.get(url, params=params, allow_redirects=False)

    # something like https://bugzilla.mozilla.org/buglist.cgi?bug_id=1493711,1502766,1499908
    url = r.headers['Location']

    return url.split('=')[1].split(',')


def get_flag(version, name, channel):
    if name in ['status', 'tracking']:
        if channel == 'esr':
            return 'cf_{}_firefox_esr{}'.format(name, version)
        return 'cf_{}_firefox{}'.format(name, version)
    elif name == 'approval':
        if channel == 'esr':
            return 'approval-mozilla-esr{}'.format(version)
        return 'approval-mozilla-{}'.format(channel)


def get_needinfo(bug, days=-1):
    now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    for flag in bug.get('flags', []):
        if flag.get('name', '') == 'needinfo' and flag['status'] == '?':
            date = flag['modification_date']
            date = dateutil.parser.parse(date)
            if (now - date).days >= days:
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


def get_default_assignees():
    global _DEFAULT_ASSIGNEES
    if _DEFAULT_ASSIGNEES is not None:
        return _DEFAULT_ASSIGNEES

    # accessible is the union of:
    #  selectable (all product we can see)
    #  enterable (all product a user can file bugs into).
    prods = get_config('common', 'products')
    url = 'https://bugzilla.mozilla.org/rest/product'
    params = {
        'type': 'accessible',
        'include_fields': ['name', 'components.name', 'components.default_assigned_to'],
        'names': prods,
    }
    r = requests.get(url, params=params)
    products = r.json()['products']
    _DEFAULT_ASSIGNEES = {}
    for prod in products:
        prod_name = prod['name']
        _DEFAULT_ASSIGNEES[prod_name] = dap = {}
        for comp in prod['components']:
            comp_name = comp['name']
            assignee = comp['default_assigned_to']
            dap[comp_name] = assignee
    return _DEFAULT_ASSIGNEES


def organize(bugs, columns, key=None):
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

    return sorted(res, key=mykey if not key else key)


def merge_bz_changes(c1, c2):
    if not c1:
        return c2
    if not c2:
        return c1

    assert set(c1.keys()).isdisjoint(
        c2.keys()
    ), 'Merge changes with common keys is not a good idea'
    c = copy.deepcopy(c1)
    c.update(c2)

    return c


def is_test_file(path):
    e = os.path.splitext(path)[1][1:].lower()
    return 'test' in path and e not in {'ini', 'list', 'in', 'py', 'json', 'manifest'}


def get_better_name(name):
    if not name:
        return ''

    def repl(m):
        if m.start(0) == 0:
            return m.group(0)
        return ''

    if name.startswith('Nobody;'):
        s = 'Nobody'
    else:
        s = PAR_PAT.sub('', name)
        s = BRA_PAT.sub('', s)
        s = DIA_PAT.sub('', s)
        s = COL_PAT.sub(repl, s)
        s = UTC_PAT.sub('', s)
        s = s.strip()
        if s.startswith(':'):
            s = s[1:]
    return s.encode('utf-8').decode('utf-8')


def is_backout(json):
    return json.get('backedoutby', '') != '' or bool(BACKOUT_PAT.search(json['desc']))


def get_pushlog(startdate, enddate, channel='nightly'):
    """Get the pushlog from hg.mozilla.org"""
    # Get the pushes where startdate <= pushdate <= enddate
    # pushlog uses strict inequality, it's why we add +/- 1 second
    fmt = '%Y-%m-%d %H:%M:%S'
    startdate -= relativedelta(seconds=1)
    startdate = startdate.strftime(fmt)
    enddate += relativedelta(seconds=1)
    enddate = enddate.strftime(fmt)
    url = '{}/json-pushes'.format(Mercurial.get_repo_url(channel))
    r = requests.get(
        url,
        params={'startdate': startdate, 'enddate': enddate, 'version': 2, 'full': 1},
    )
    return r.json()


def get_bugs_from_desc(desc):
    """Get a bug number from the patch description"""
    return BUG_PAT.findall(desc)


def get_bugs_from_pushlog(startdate, enddate, channel='nightly'):
    pushlog = get_pushlog(startdate, enddate, channel=channel)
    bugs = set()
    for push in pushlog['pushes'].values():
        for chgset in push['changesets']:
            if chgset.get('backedoutby', '') != '':
                continue
            desc = chgset['desc']
            for bug in get_bugs_from_desc(desc):
                bugs.add(bug)
    return bugs


def get_checked_versions():
    versions = get_current_versions()
    v = [int(versions[k]) for k in ['release', 'beta', 'central']]
    if v[0] + 2 == v[1] + 1 == v[2]:
        return versions

    from . import logger

    logger.info('Not consecutive versions in product/details')
    return None


def get_info_from_hg(json):
    res = {}
    push = json['pushdate'][0]
    push = datetime.datetime.utcfromtimestamp(push)
    push = lmdutils.as_utc(push)
    res['date'] = lmdutils.get_date_str(push)
    res['backedout'] = json.get('backedoutby', '') != ''
    m = BUG_PAT.search(json['desc'])
    res['bugid'] = m.group(1) if m else ''

    return res


def bz_ignore_case(s):
    return '[' + ']['.join(c + c.upper() for c in s) + ']'


def check_product_component(data, bug):
    prod = bug['product']
    comp = bug['component']
    pc = prod + '::' + comp
    return pc in data or comp in data


def get_components(data):
    res = []
    for comp in data:
        if '::' in comp:
            _, comp = comp.split('::', 1)
        res.append(comp)
    return res


def ireplace(old, repl, text):
    return re.sub('(?i)' + re.escape(old), lambda m: repl, text)
