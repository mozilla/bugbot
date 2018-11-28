# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import dateutil.parser
from dateutil.relativedelta import relativedelta
from jinja2 import Environment, FileSystemLoader
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
import six
from auto_nag import mail, utils
from auto_nag.nag_me import Nag


class BzCleaner(object):
    def __init__(self):
        super(BzCleaner, self).__init__()
        self.has_autofix = False
        self.last_comment = {}
        self.no_manager = set()
        self.assignees = {}
        self.needinfos = {}
        self.auto_needinfo = {}

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

    def add_assignee(self, bugid, name):
        self.assignees[str(bugid)] = name

    def add_needinfo(self, bugid, name):
        bugid = str(bugid)
        if bugid in self.needinfos:
            self.needinfos[bugid].add(name)
        else:
            self.needinfos[bugid] = set([name])

    def get_needinfo_for_template(self):
        res = {}
        for bugid, ni in self.needinfos.items():
            res[bugid] = '(' + ', '.join('needinfo? ' + x for x in sorted(ni)) + ')'
        return res

    def has_assignee(self):
        return False

    def has_needinfo(self):
        return False

    def get_mail_to_auto_ni(self, bug):
        return None

    def get_max_ni(self):
        return -1

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
        return []

    def get_summary(self, bug):
        return '...' if bug['groups'] else bug['summary']

    def has_default_products(self):
        return True

    def handle_bug(self, bug):
        """Implement this function to get all the bugs from the query"""
        pass

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
        self.handle_bug(bug)

        if isinstance(self, Nag):
            bug = self.set_people_to_nag(bug)
            if not bug:
                return

        auto_ni = self.get_mail_to_auto_ni(bug)
        self.add_auto_ni(bug['id'], auto_ni)

        if self.ignore_bug_summary():
            data.append(bug['id'])
        else:
            data.append((bug['id'], self.get_summary(bug)))

        if self.has_assignee():
            real = bug['assigned_to_detail']['real_name']
            bugid = str(bug['id'])
            self.add_assignee(bugid, real)

        if self.has_needinfo():
            bugid = str(bug['id'])
            for flag in utils.get_needinfo(bug):
                self.add_needinfo(bugid, flag['requestee'])

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

        if self.has_assignee() and 'assigned_to' not in params['include_fields']:
            params['include_fields'].append('assigned_to')

        if self.has_needinfo() and 'flags' not in params['include_fields']:
            params['include_fields'].append('flags')

        if self.filter_no_nag_keyword():
            n = utils.get_last_field_num(params)
            n = str(n)
            params.update(
                {
                    'f' + n: 'status_whiteboard',
                    'o' + n: 'notsubstring',
                    'v' + n: '[no-nag]',
                }
            )

        if self.has_default_products():
            params['product'] = utils.get_config('common', 'products')

    def get_bugs(self, date='today', bug_ids=[]):
        """Get the bugs"""
        bugids = self.get_data()
        params = self.get_bz_params(date)
        self.amend_bzparams(params, bug_ids)

        Bugzilla(
            params,
            bughandler=self.bughandler,
            bugdata=bugids,
            timeout=utils.get_config(self.name(), 'bz_query_timeout'),
        ).get_data().wait()

        self.get_comments(bugids)

        return sorted(bugids) if isinstance(bugids, list) else bugids

    def get_comment_data(self):
        return None

    def commenthandler(self, bug, bugid, data):
        return

    def _commenthandler(self, *args):
        if len(args) == 2:
            bug, bugid = args
            data = None
        else:
            bug, bugid, data = args

        comments = bug['comments']
        if self.has_last_comment_time():
            if comments:
                # get the timestamp of the last comment
                self.last_comment[bugid] = str(
                    dateutil.parser.parse(comments[-1]['time'])
                )
            else:
                self.last_comment[bugid] = ''

        if data is not None:
            self.commenthandler(bug, bugid, data)

    def get_comments(self, bugids):
        """Get the bugs comments"""
        data = self.get_comment_data()
        if data is not None or self.has_last_comment_time():
            bugids = self.get_list_bugs(bugids)
            Bugzilla(
                bugids=bugids, commenthandler=self._commenthandler, commentdata=data
            ).get_data().wait()

    def has_last_comment_time(self):
        return False

    def get_last_comment_time(self):
        return self.last_comment

    def get_list_bugs(self, bugs):
        if self.ignore_bug_summary():
            return list(map(str, bugs))
        return [str(x) for x, _ in bugs]

    def set_needinfo(self, bugs, dryrun):
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
                if dryrun:
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
        self.set_needinfo(bugs, dryrun)

        change = self.get_autofix_change()
        if change:
            self.has_autofix = True
            if not self.has_individual_autofix():
                bugids = self.get_list_bugs(bugs)
                if dryrun:
                    print(
                        'The bugs: {}\n will be autofixed with:\n{}'.format(
                            bugids, change
                        )
                    )
                else:
                    Bugzilla(bugids).put(change)
            else:
                if dryrun:
                    for bugid, ch in change.items():
                        print(
                            'The bug: {} will be autofixed with: {}'.format(bugid, ch)
                        )
                else:
                    for bugid, ch in change.items():
                        Bugzilla([str(bugid)]).put(ch)

        return bugs

    def get_email(self, bztoken, date, dryrun, bug_ids=[]):
        """Get title and body for the email"""
        Bugzilla.TOKEN = bztoken
        bugids = self.get_bugs(date=date, bug_ids=bug_ids)
        bugids = self.autofix(bugids, dryrun)
        if bugids:
            extra = self.get_extra_for_template()
            env = Environment(loader=FileSystemLoader('templates'))
            template = env.get_template(self.template())
            message = template.render(
                date=date,
                bugids=bugids,
                extra=extra,
                str=str,
                plural=utils.plural,
                no_manager=self.no_manager,
                last_comment=self.last_comment,
                assignees=self.assignees,
                needinfos=self.get_needinfo_for_template(),
            )
            common = env.get_template('common.html')
            body = common.render(message=message)
            return self.get_email_subject(date), body
        return None, None

    def send_email(self, date='today', dryrun=False):
        """Send the email"""
        if date:
            date = lmdutils.get_date(date)
            if not self.must_run(lmdutils.get_date_ymd(date)):
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
                self.send_mails(date, title, dryrun=dryrun)
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
