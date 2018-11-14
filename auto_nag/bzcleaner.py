# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from dateutil.relativedelta import relativedelta
from jinja2 import Environment, FileSystemLoader
import json
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
import six
from auto_nag.bugzilla.utils import get_config_path
from auto_nag import mail, utils


class BzCleaner(object):

    def __init__(self):
        pass

    def description(self):
        """Get the description for the help"""
        return ''

    def name(self):
        """Get the tool name"""
        return ''

    def template(self):
        """Get the html template filename"""
        return ''

    def subject(self):
        """Get the partial email subject"""
        return ''

    def get_email_subject(self, date):
        """Get the email subject with a date or not"""
        if date:
            return '[autonag] {} for the {}'.format(self.subject(), date)
        return '[autonag] {}'.format(self.subject())

    def ignore_date(self):
        """Should we ignore the date ?"""
        return False

    def ignore_bug_summary(self):
        """Should we ignore the bug summary ?"""
        return True

    def get_dates(self, date):
        """Get the dates for the bugzilla query (changedafter and changedbefore fields)"""
        date = lmdutils.get_date_ymd(date)
        lookup = utils.get_config(self.name(), 'days_lookup', 7)
        start_date = date - relativedelta(days=lookup)
        end_date = date + relativedelta(days=1)

        return start_date, end_date

    def get_extra_for_template(self):
        """Get extra data to put in the template"""
        return {}

    def get_config(self, entry, default=None):
        return utils.get_config(self.name(), entry, default=default)

    def get_bz_params(self, date):
        """Get the Bugzilla parameters for the search query"""
        return {}

    def get_data(self):
        """Get the data structure to use in the bughandler"""
        return []

    def get_summary(self, bug):
        return '' if bug['groups'] else bug['summary']

    def bughandler(self, bug, data):
        """bug handler for the Bugzilla query"""
        if self.ignore_bug_summary():
            data.append(bug['id'])
        else:
            data.append((bug['id'], self.get_summary(bug)))

    def amend_bzparams(self, params, bug_ids):
        """Amend the Bugzilla params"""
        if 'include_fields' in params:
            fields = params['include_fields']
            if isinstance(fields, list):
                if 'id' not in fields:
                    fields.append('id')
            elif isinstance(fields, six.string_types):
                if fields != 'id':
                    params['include_fields'] = [fields, 'id']
            else:
                params['include_fields'] = [fields, 'id']
        else:
            params['include_fields'] = ['id']

        if bug_ids:
            params['bug_id'] = bug_ids

        if not self.ignore_bug_summary():
            params['include_fields'] += ['summary', 'groups']

    def get_bugs(self, date='today', bug_ids=[]):
        """Get the bugs"""
        bugids = self.get_data()
        params = self.get_bz_params(date)
        self.amend_bzparams(params, bug_ids)

        Bugzilla(params,
                 bughandler=self.bughandler,
                 bugdata=bugids,
                 timeout=utils.get_config(self.name(), 'bz_query_timeout')).get_data().wait()

        return sorted(bugids) if isinstance(bugids, list) else bugids

    def get_list_bugs(self, bugs):
        if self.ignore_bug_summary():
            return list(map(str, bugs))
        return [str(x) for x, _ in bugs]

    def get_autofix_change(self):
        """Get the change to do to autofix the bugs"""
        return {}

    def autofix(self, bugs):
        """Autofix the bugs according to what is returned by get_autofix_change"""
        change = self.get_autofix_change()
        if change:
            bugids = self.get_list_bugs(bugs)
            Bugzilla(bugids).put(change)

        return bugs

    def get_login_info(self):
        """Get the login info"""
        with open(get_config_path(), 'r') as In:
            return json.load(In)

    def get_email(self, bztoken, date, dryrun, bug_ids=[]):
        """Get title and body for the email"""
        Bugzilla.TOKEN = bztoken
        bugids = self.get_bugs(date=date, bug_ids=bug_ids)
        if not dryrun:
            bugids = self.autofix(bugids)
        if bugids:
            env = Environment(loader=FileSystemLoader('templates'))
            template = env.get_template(self.template())
            message = template.render(date=date,
                                      bugids=bugids,
                                      extra=self.get_extra_for_template())
            common = env.get_template('common.html')
            body = common.render(message=message)
            return self.get_email_subject(date), body
        return None, None

    def send_email(self, date='today', dryrun=False):
        """Send the email"""
        login_info = self.get_login_info()
        if date:
            date = lmdutils.get_date(date)
        title, body = self.get_email(login_info['bz_api_key'], date, dryrun)
        if title:
            mail.send(login_info['ldap_username'],
                      utils.get_config(self.name(), 'receivers'),
                      title, body,
                      html=True, login=login_info, dryrun=dryrun)
        else:
            name = self.name().upper()
            if date:
                print('{}: No data for {}'.format(name, date))
            else:
                print('{}: No data'.format(name))

    def get_args_parser(self):
        """Get the argumends from the command line"""
        parser = argparse.ArgumentParser(description=self.description())
        parser.add_argument('-d', '--dryrun', dest='dryrun',
                            action='store_true', default=False,
                            help='Just do the query, and print emails to console without emailing anyone')  # NOQA

        if not self.ignore_date():
            parser.add_argument('-D', '--date', dest='date',
                                action='store', default='today',
                                help='Date for the query')

        return parser

    def run(self):
        """Run the tool"""
        args = self.get_args_parser().parse_args()
        date = '' if self.ignore_date() else args.date
        self.send_email(date=date, dryrun=args.dryrun)
