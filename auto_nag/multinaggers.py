# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from jinja2 import Environment, FileSystemLoader
from libmozdata import utils as lmdutils
import time
from auto_nag import mail, utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.nag_me import Nag


class MultiNaggers(object):
    def __init__(self, *args):
        super(MultiNaggers, self).__init__()
        for arg in args:
            assert isinstance(arg, Nag)
            assert isinstance(arg, BzCleaner)
        self.naggers = list(args)

    def description(self):
        return ''

    def title(self):
        return ''

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
        args = self.get_args_parser().parse_args()
        self.date = lmdutils.get_date_ymd(args.date)
        for nagger in self.naggers:
            nagger.send_nag_mail = False
            nagger.run()
        self.gather(args.dryrun)

    def gather(self, dryrun):
        env = Environment(loader=FileSystemLoader('templates'))
        common = env.get_template('common.html')
        login_info = utils.get_login_info()
        From = Nag.get_from()
        Default_Cc = Nag.get_cc()

        all_mails = {}
        for nagger in self.naggers:
            mails = nagger.prepare_mails()
            for m in mails:
                manager = m['manager']
                if manager not in all_mails:
                    all_mails[manager] = {'to': m['to'], 'body': m['body']}
                else:
                    all_mails[manager]['to'] |= m['to']
                    all_mails[manager]['body'] += '\n' + m['body']

        for manager, m in all_mails.items():
            Cc = Default_Cc.copy()
            Cc.add(manager)
            body = common.render(message=m['body'])
            mail.send(
                From,
                list(sorted(m['to'])),
                self.title(),
                body,
                Cc=list(sorted(Cc)),
                html=True,
                login=login_info,
                dryrun=dryrun,
            )
            time.sleep(1)
