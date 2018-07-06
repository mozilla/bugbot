# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from dateutil.relativedelta import relativedelta
from jinja2 import Environment, FileSystemLoader
import json
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
import re
from auto_nag.bugzilla.utils import get_config_path
from auto_nag import mail, utils
from auto_nag.scripts.common import get_login_info


COMMENTS_PAT = re.compile('^>.*[\n]?', re.MULTILINE)
HAS_UPLIFT_PAT = re.compile('(Feature/Bug causing the regression)|(feature/regressing bug #)', re.I)
UPLIFT1_PAT = re.compile('[\[]?Feature/Bug causing the regression[\]]?:\n*(?:(?:[ \t]*)|(?:[^0-9]*bug[ \t]*))([0-9]+)[^\n]*$', re.MULTILINE | re.I)
UPLIFT2_PAT = re.compile('[\[]?Bug caused by[\]]? \(feature/regressing bug #\):\n*(?:(?:[ \t]*)|(?:[^0-9]*bug[ \t]*))([0-9]+)[^\n]*$', re.MULTILINE | re.I)
REG_BY_BUG_PAT = re.compile('[ \t]regress[^0-9\.,;\n]+(?:bug[ \t]*)([0-9]+)(?:[^\.\n\?]*[\.\n])?', re.I)
CAUSED_BY_PAT = re.compile('caused by bug[ \t]*([0-9]+)', re.I)
REG_PAT = re.compile('(regression is)|(regression range)|(regressed build)|(mozregression)|(this is a regression)|(this regression)|(is a recent regression)|(regression version is)|(regression[- ]+window)', re.I)


def get_bz_params(date):
    date = lmdutils.get_date_ymd(date)
    lookup = utils.get_config('regressions', 'days_lookup', 7)
    prod_blacklist = utils.get_config('regressions', 'product_blacklist', [])
    prod_blacklist = ' '.join(prod_blacklist)
    resolution_blacklist = utils.get_config('regressions', 'resolution_blacklist', [])
    resolution_blacklist = ' '.join(resolution_blacklist)
    start_date = date - relativedelta(days=lookup)
    end_date = date + relativedelta(days=1)
    fields = ['id', 'keywords', 'cf_has_regression_range']
    params = {'include_fields': fields,
              'f1': 'keywords',
              'o1': 'notsubstring',
              'v1': 'regression',
              'f2': 'longdesc',
              'o2': 'anywordssubstr',
              'v2': 'regress caus',
              'f3': 'product',
              'o3': 'nowords',
              'v3': prod_blacklist,
              'f4': 'resolution',
              'o4': 'nowords',
              'v4': resolution_blacklist,
              'f5': 'longdesc',
              'o5': 'changedafter',
              'v5': start_date,
              'f6': 'longdesc',
              'o6': 'changedbefore',
              'v6': end_date}

    return params


def get_bugs(date='today'):
    # the search query can be long to evaluate
    TIMEOUT = 240

    def bug_handler(bug, data):
        keywords = data.get('keywords', [])
        if 'regressionwindow-wanted' in keywords:
            data['regressions'].add(bug['id'])
        else:
            has_regression_range = data.get('cf_has_regression_range', '---')
            if has_regression_range == 'yes':
                data['regressions'].add(bug['id'])
            else:
                data['others'].append(bug['id'])

    data = {'regressions': set(),
            'others': []}

    Bugzilla(get_bz_params(date),
             bughandler=bug_handler,
             bugdata=data,
             timeout=TIMEOUT).get_data().wait()

    return data


def clean_comment(comment):
    return COMMENTS_PAT.sub('', comment)


def has_uplift(comment):
    m = HAS_UPLIFT_PAT.search(comment)
    return bool(m)


def find_bug_reg(comment):
    if has_uplift(comment):
        pats = [UPLIFT1_PAT, UPLIFT2_PAT]
        for pat in pats:
            m = pat.search(comment)
            if m:
                return m.group(1)
        return ''
    else:
        pats = [REG_BY_BUG_PAT, CAUSED_BY_PAT]
        for pat in pats:
            m = pat.search(comment)
            if m:
                return m.group(1)
    return None


def has_reg_str(comment):
    m = REG_PAT.search(comment)
    return bool(m)


def analyze_comments(bugids):
    """Analyze the comments to find regression"""

    def comment_handler(bug, bugid, data):
        bugid = int(bugid)
        for comment in bug['comments']:
            comment = clean_comment(comment['text'])
            reg_bug = find_bug_reg(comment)
            if reg_bug is None:
                if has_reg_str(comment):
                    data[bugid] = True
                    break
            elif reg_bug:
                data[bugid] = True
                break

    data = {bugid: False for bugid in bugids}
    Bugzilla(bugids=bugids,
             commenthandler=comment_handler,
             commentdata=data,
             comment_include_fields=['text']).get_data().wait()

    return data


def analyze_history(bugids):

    def history_handler(history, data):
        bugid = int(history['id'])
        for h in history['history']:
            changes = h.get('changes', [])
            for change in changes:
                if change['field_name'] == 'keywords' and change['removed'] == 'regression':
                    data.add(bugid)
                    return

    data = set()
    Bugzilla(bugids=bugids,
             historyhandler=history_handler,
             historydata=data).get_data().wait()

    return bugids - data


def get_reg(date='today'):
    bugids = get_bugs(date=date)
    data = analyze_comments(bugids['others'])
    reg_bugids = {bugid for bugid, reg in data.items() if reg}
    reg_bugids = analyze_history(reg_bugids)
    reg_bugids |= bugids['regressions']

    return sorted(reg_bugids, reverse=True)

def get_email(bztoken, date):
    Bugzilla.TOKEN = bztoken
    bugids = get_reg(date=date)
    if bugids:
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('regression.html')
        body = template.render(date=date,
                               bugids=bugids)
        title = '[autonag] Bugs with missing regression keyword for the {}'.format(date)
        return title, body
    return None, None


def send_email(date='today', dryrun=False):
    login_info = get_login_info()
    date = lmdutils.get_date(date)
    title, body = get_email(login_info['bz_api_key'], date)
    if title:
        mail.send(login_info['ldap_username'],
                  utils.get_config('regressions', 'receivers', ['sylvestre@mozilla.com']),
                  title, body,
                  html=True, login=login_info, dryrun=dryrun)
    else:
        print('REGRESSION: No data for {}'.format(date))


if __name__ == '__main__':
    description = 'Get bugs with missing regression keyword'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-d', '--dryrun', dest='dryrun',
                        action='store_true', default=False,
                        help='Just do the query, and print emails to console without emailing anyone')
    parser.add_argument('-D', '--date', dest='date',
                        action='store', default='today',
                        help='Date for the query')
    args = parser.parse_args()
    send_email(date=args.date, dryrun=args.dryrun)
