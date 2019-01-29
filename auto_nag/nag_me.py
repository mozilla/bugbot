# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from jinja2 import Environment, FileSystemLoader
from auto_nag import mail, utils
from auto_nag.people import People
from auto_nag.escalation import Escalation


class Nag(object):
    def __init__(self):
        super(Nag, self).__init__()
        self.people = People()
        self.send_nag_mail = True
        self.data = {}
        self.nag_date = None
        self.white_list = []
        self.black_list = []
        self.escalation = Escalation(self.people)

    @staticmethod
    def get_from():
        return utils.get_config('auto_nag', 'from', 'release-mgmt@mozilla.com')

    @staticmethod
    def get_cc():
        return set(utils.get_config('auto_nag', 'cc', []))

    def get_priority(self, bug):
        tracking = bug[self.tracking]
        if tracking == 'blocking':
            return 'high'
        return 'normal'

    def filter_bug(self, priority):
        days = (utils.get_next_release_date() - self.nag_date).days
        weekday = self.nag_date.weekday()
        return self.escalation.filter(priority, days, weekday)

    def get_people(self):
        return self.people

    def set_people_to_nag(self, bug):
        return bug

    def escalate(self, person, priority, **kwargs):
        days = (utils.get_next_release_date() - self.nag_date).days
        return self.escalation.get_supervisor(priority, days, person, **kwargs)

    def add(self, person, bug_data, priority='default', **kwargs):
        if not self.people.is_mozilla(person):
            return False

        manager = self.escalate(person, priority, **kwargs)
        return self.add_couple(person, manager, bug_data)

    def add_couple(self, person, manager, bug_data):
        person = self.people.get_moz_mail(person)

        if manager in self.data:
            data = self.data[manager]
        else:
            self.data[manager] = data = {}
        if person in data:
            data[person].append(bug_data)
        else:
            data[person] = [bug_data]

        return True

    def nag_template(self):
        return ''

    def get_extra_for_nag_template(self):
        return {}

    def _is_in_list(self, mail, _list):
        for manager in _list:
            if self.people.is_under(mail, manager):
                return True
        return False

    def is_under(self, mail):
        if not self.white_list:
            if not self.black_list:
                return True
            return not self._is_in_list(mail, self.black_list)
        if not self.black_list:
            return self._is_in_list(mail, self.white_list)
        return self._is_in_list(mail, self.white_list) and not self._is_in_list(
            mail, self.black_list
        )

    def send_mails(self, title, last_comment, assignees, dryrun=False):
        self.last_comment_nag = last_comment
        self.assignees_nag = assignees
        if not self.send_nag_mail:
            return

        env = Environment(loader=FileSystemLoader('templates'))
        common = env.get_template('common.html')
        login_info = utils.get_login_info()
        From = Nag.get_from()
        Default_Cc = Nag.get_cc()
        mails = self.prepare_mails()

        for m in mails:
            Cc = Default_Cc.copy()
            if m['manager']:
                Cc.add(m['manager'])
            body = common.render(message=m['body'], query_url=None, has_table=True)
            mail.send(
                From,
                sorted(m['to']),
                title,
                body,
                Cc=sorted(Cc),
                html=True,
                login=login_info,
                dryrun=dryrun,
            )

    def prepare_mails(self):
        if not self.data:
            return []

        template = self.nag_template()
        if not template:
            return []

        extra = self.get_extra_for_nag_template()
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template(template)
        mails = []
        for manager, info in self.data.items():
            data = []
            To = sorted(info.keys())
            for person in To:
                bug_data = info[person]
                data += bug_data

            body = template.render(
                date=self.nag_date,
                extra=extra,
                plural=utils.plural,
                enumerate=enumerate,
                data=data,
                assignees=self.assignees_nag,
                last_comment=self.last_comment_nag,
            )

            m = {'manager': manager, 'to': set(info.keys()), 'body': body}
            mails.append(m)

        return mails
