# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from datetime import datetime
import dateutil.parser
from dateutil.relativedelta import relativedelta
import humanize
from jinja2 import Environment, FileSystemLoader
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
import pytz
import six
from auto_nag import mail, utils
from auto_nag.nag_me import Nag


class BzCleaner(object):
    def __init__(self):
        super(BzCleaner, self).__init__()
        self.has_autofix = False
        self.no_manager = set()
        self.auto_needinfo = {}
        self.has_flags = False
        self.test_mode = utils.get_config('common', 'test', False)

    def description(self):
        """Get the description for the help"""
        return ''

    def name(self):
        """Get the tool name"""
        return ''

    def needinfo_template(self):
        """Get the txt template filename"""
        return ''

    def template(self):
        """Get the html template filename"""
        return ''

    def subject(self):
        """Get the partial email subject"""
        return ''

    def get_email_subject(self, date):
        """Get the email subject with a date or not"""
        af = '[autofix]' if self.has_autofix else ''
        if date:
            return '[autonag]{} {} for the {}'.format(af, self.subject(), date)
        return '[autonag]{} {}'.format(af, self.subject())

    def ignore_date(self):
        """Should we ignore the date ?"""
        return False

    def ignore_bug_summary(self):
        """Should we ignore the bug summary ?"""
        return True

    def must_run(self, date):
        """Check if the tool must run for this date"""
        return True

    def filter_no_nag_keyword(self):
        """If True, then remove the bugs with [no-nag] in whiteboard from the bug list"""
        return True

    def add_no_manager(self, bugid):
        self.no_manager.add(str(bugid))

    def has_assignee(self):
        return False

    def has_needinfo(self):
        return False

    def get_mail_to_auto_ni(self, bug):
        return None

    def all_include_fields(self):
        return False

    def get_max_ni(self):
        return -1

    def ignore_meta(self):
        return False

    def columns(self):
        """The fields to get for the columns in email report"""
        if self.ignore_bug_summary():
            return ['id']
        return ['id', 'summary']

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

    def get_extra_for_needinfo_template(self):
        """Get extra data to put in the needinfo template"""
        return {}

    def get_config(self, entry, default=None):
        return utils.get_config(self.name(), entry, default=default)

    def get_bz_params(self, date):
        """Get the Bugzilla parameters for the search query"""
        return {}

    def get_data(self):
        """Get the data structure to use in the bughandler"""
        return {}

    def get_summary(self, bug):
        return '...' if bug['groups'] else bug['summary']

    def has_default_products(self):
        return True

    def has_product_component(self):
        return False

    def get_product_component(self):
        return self.prod_comp

    def handle_bug(self, bug, data):
        """Implement this function to get all the bugs from the query"""
        return bug

    def get_auto_ni_blacklist(self):
        return set()

    def add_auto_ni(self, bugid, data):
        if not data:
            return

        ni_mail = data['mail']
        if ni_mail in self.get_auto_ni_blacklist():
            return
        if ni_mail in self.auto_needinfo:
            max_ni = self.get_max_ni()
            info = self.auto_needinfo[ni_mail]
            if max_ni <= 0 or len(info['bugids']) < max_ni:
                info['bugids'].append(str(bugid))
        else:
            self.auto_needinfo[ni_mail] = {
                'nickname': data['nickname'],
                'bugids': [str(bugid)],
            }

    def bughandler(self, bug, data):
        """bug handler for the Bugzilla query"""
        if self.handle_bug(bug, data) is None:
            return

        bugid = str(bug['id'])
        res = {'id': bugid}

        auto_ni = self.get_mail_to_auto_ni(bug)
        self.add_auto_ni(bugid, auto_ni)

        if not self.ignore_bug_summary():
            res['summary'] = self.get_summary(bug)

        if self.has_assignee():
            real = bug['assigned_to_detail']['real_name']
            if utils.is_no_assignee(bug['assigned_to']):
                real = 'nobody'
            res['assignee'] = real

        if self.has_needinfo():
            s = set()
            for flag in utils.get_needinfo(bug):
                s.add(flag['requestee'])
            res['needinfos'] = sorted(s)

        if self.has_product_component():
            for k in ['product', 'component']:
                res[k] = bug[k]

        if isinstance(self, Nag):
            bug = self.set_people_to_nag(bug, res)
            if not bug:
                return

        data[bugid] = res

    def amend_bzparams(self, params, bug_ids):
        """Amend the Bugzilla params"""
        if not self.all_include_fields():
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

            if not self.ignore_bug_summary():
                params['include_fields'] += ['summary', 'groups']

            if self.has_assignee() and 'assigned_to' not in params['include_fields']:
                params['include_fields'].append('assigned_to')

            if self.has_product_component():
                if 'product' not in params['include_fields']:
                    params['include_fields'].append('product')
                if 'component' not in params['include_fields']:
                    params['include_fields'].append('component')

            if self.has_needinfo() and 'flags' not in params['include_fields']:
                params['include_fields'].append('flags')

        if bug_ids:
            params['bug_id'] = bug_ids

        if self.filter_no_nag_keyword():
            n = utils.get_last_field_num(params)
            params.update(
                {
                    'f' + n: 'status_whiteboard',
                    'o' + n: 'notsubstring',
                    'v' + n: '[no-nag]',
                }
            )

        if self.ignore_meta():
            n = utils.get_last_field_num(params)
            params.update({'f' + n: 'keywords', 'o' + n: 'nowords', 'v' + n: 'meta'})

        if self.has_default_products():
            params['product'] = utils.get_config('common', 'products')

        self.has_flags = 'flags' in params.get('include_fields', [])

    def get_bugs(self, date='today', bug_ids=[]):
        """Get the bugs"""
        bugs = self.get_data()
        params = self.get_bz_params(date)
        self.amend_bzparams(params, bug_ids)
        self.query_url = utils.get_bz_search_url(params)

        if isinstance(self, Nag):
            self.query_params = params

        Bugzilla(
            params,
            bughandler=self.bughandler,
            bugdata=bugs,
            timeout=utils.get_config(self.name(), 'bz_query_timeout'),
        ).get_data().wait()

        self.get_comments(bugs)

        return bugs  # TODO: attention au reverse_order (config/tools.json)

    def commenthandler(self, bug, bugid, data):
        return

    def _commenthandler(self, bug, bugid, data):
        comments = bug['comments']
        bugid = str(bugid)
        if self.has_last_comment_time():
            if comments:
                # get the timestamp of the last comment
                today = pytz.utc.localize(datetime.utcnow())
                dt = dateutil.parser.parse(comments[-1]['time'])
                data[bugid]['last_comment'] = humanize.naturaldelta(today - dt)
            else:
                data[bugid]['last_comment'] = ''

        self.commenthandler(bug, bugid, data)

    def get_comments(self, bugs):
        """Get the bugs comments"""
        if self.has_last_comment_time():
            bugids = self.get_list_bugs(bugs)
            Bugzilla(
                bugids=bugids, commenthandler=self._commenthandler, commentdata=bugs
            ).get_data().wait()
        return bugs

    def has_last_comment_time(self):
        return False

    def get_list_bugs(self, bugs):
        return [x['id'] for x in bugs.values()]

    def has_bot_set_ni(self, bug):
        if not self.has_flags:
            raise Exception
        return utils.has_bot_set_ni(bug)

    def set_needinfo(self, dryrun):
        if not self.auto_needinfo:
            return

        template_name = self.needinfo_template()
        assert bool(template_name)
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template(template_name)

        for ni_mail, info in self.auto_needinfo.items():
            nick = info['nickname']
            for bugid in info['bugids']:
                comment = template.render(
                    nickname=nick,
                    extra=self.get_extra_for_needinfo_template(),
                    plural=utils.plural,
                )
                data = {
                    'comment': {'body': comment},
                    'flags': [
                        {
                            'name': 'needinfo',
                            'requestee': ni_mail,
                            'status': '?',
                            'new': 'true',
                        }
                    ],
                }
                if dryrun or self.test_mode:
                    print('Auto needinfo {}: {}'.format(bugid, data))
                else:
                    Bugzilla(bugids=[bugid]).put(data)

    def has_individual_autofix(self):
        """Check if the autofix is the same for all bugs or different for each bug"""
        return False

    def get_autofix_change(self):
        """Get the change to do to autofix the bugs"""
        return {}

    def autofix(self, bugs, dryrun):
        """Autofix the bugs according to what is returned by get_autofix_change"""
        self.set_needinfo(dryrun)

        change = self.get_autofix_change()
        if change:
            self.has_autofix = True
            if not self.has_individual_autofix():
                bugids = self.get_list_bugs(bugs)
                if dryrun or self.test_mode:
                    print(
                        'The bugs: {}\n will be autofixed with:\n{}'.format(
                            bugids, change
                        )
                    )
                else:
                    for bugid in bugids:
                        Bugzilla([bugid]).put(change)
            else:
                if dryrun or self.test_mode:
                    for bugid, ch in change.items():
                        print(
                            'The bug: {} will be autofixed with: {}'.format(bugid, ch)
                        )
                else:
                    for bugid, ch in change.items():
                        Bugzilla([str(bugid)]).put(ch)

        return bugs

    def organize(self, bugs):
        return utils.organize(bugs, self.columns())

    def get_email(self, bztoken, date, dryrun, bug_ids=[]):
        """Get title and body for the email"""
        Bugzilla.TOKEN = bztoken
        bugs = self.get_bugs(date=date, bug_ids=bug_ids)
        bugs = self.autofix(bugs, dryrun)
        if bugs:
            bugs = self.organize(bugs)
            extra = self.get_extra_for_template()
            env = Environment(loader=FileSystemLoader('templates'))
            template = env.get_template(self.template())
            message = template.render(
                date=date,
                data=bugs,
                extra=extra,
                str=str,
                enumerate=enumerate,
                plural=utils.plural,
                no_manager=self.no_manager,
            )
            common = env.get_template('common.html')
            body = common.render(
                message=message,
                query_url=self.query_url,
                has_table='<thead>' in message,
            )
            return self.get_email_subject(date), body
        return None, None

    def send_email(self, date='today', dryrun=False):
        """Send the email"""
        if date:
            date = lmdutils.get_date(date)
            d = lmdutils.get_date_ymd(date)
            if isinstance(self, Nag):
                self.nag_date = d

            if not self.must_run(d):
                return

        login_info = utils.get_login_info()
        title, body = self.get_email(login_info['bz_api_key'], date, dryrun)
        if title:
            mail.send(
                login_info['ldap_username'],
                utils.get_config(self.name(), 'receivers'),
                title,
                body,
                html=True,
                login=login_info,
                dryrun=dryrun,
            )

            if isinstance(self, Nag):
                self.send_mails(title, dryrun=dryrun)
        else:
            name = self.name().upper()
            if date:
                print('{}: No data for {}'.format(name, date))
            else:
                print('{}: No data'.format(name))

    def get_args_parser(self):
        """Get the argumends from the command line"""
        parser = argparse.ArgumentParser(description=self.description())
        parser.add_argument(
            '-d',
            '--dryrun',
            dest='dryrun',
            action='store_true',
            help='Just do the query, and print emails to console without emailing anyone',
        )

        if not self.ignore_date():
            parser.add_argument(
                '-D',
                '--date',
                dest='date',
                action='store',
                default='today',
                help='Date for the query',
            )

        return parser

    def run(self):
        """Run the tool"""
        args = self.get_args_parser().parse_args()
        date = '' if self.ignore_date() else args.date
        self.send_email(date=date, dryrun=args.dryrun)
