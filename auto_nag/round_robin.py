# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import bisect
import json
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import BugzillaUser

from auto_nag import utils
from auto_nag.people import People


class BadFallback(Exception):
    pass


class RoundRobin(object):
    def __init__(self, rr=None, people=People()):
        self.feed(rr=rr)
        self.nicks = {}
        self.people = people

    def feed(self, rr=None):
        self.data = {}
        filenames = {}
        if rr is None:
            rr = {}
            for team, path in utils.get_config(
                'round-robin', "teams", default={}
            ).items():
                with open('./auto_nag/scripts/configs/{}'.format(path), 'r') as In:
                    rr[team] = json.load(In)
                    filenames[team] = path

        # rr is dictionary:
        # - doc -> documentation
        # - triagers -> dictionary: Real Name -> {bzmail: bugzilla email, nick: bugzilla nickname}
        # - components -> dictionary: Product::Component -> strategy name
        # - strategies: dictionay: {duty en date -> Real Name}

        # Get all the strategies for each team
        for team, data in rr.items():
            if 'doc' in data:
                del data['doc']
            strategies = {}
            triagers = data['triagers']
            fallback_bzmail = triagers['Fallback']['bzmail']
            path = filenames.get(team, '')

            # collect strategies
            for pc, strategy in data['components'].items():
                strategy_data = data[strategy]
                if strategy not in strategies:
                    strategies[strategy] = strategy_data

            # rewrite strategy to have a sorted list of end dates
            for strat_name, strategy in strategies.items():
                if 'doc' in strategy:
                    del strategy['doc']
                date_name = []

                # end date and real name of the triager
                for date, name in strategy.items():
                    # collect the tuple (end_date, bzmail)
                    date = lmdutils.get_date_ymd(date)
                    bzmail = triagers[name]['bzmail']
                    date_name.append((date, bzmail))

                # we sort the list to use bisection to find the triager
                date_name = sorted(date_name)
                strategies[strat_name] = {
                    'dates': [d for d, _ in date_name],
                    'mails': [m for _, m in date_name],
                    'fallback': fallback_bzmail,
                    'filename': path,
                }

            # finally self.data is a dictionary:
            # - Product::Component -> dictionary {dates: sorted list of end date
            #                                     mails: list
            #                                     fallback: who to nag when we've nobody
            #                                     filename: the file containing strategy}
            for pc, strategy in data['components'].items():
                self.data[pc] = strategies[strategy]

    def get_nick(self, bzmail):
        if bzmail not in self.nicks:

            def handler(user):
                self.nicks[bzmail] = user['nick']

            BugzillaUser(user_names=[bzmail], user_handler=handler).wait()

        return self.nicks[bzmail]

    def is_mozilla(self, bzmail):
        return self.people.is_mozilla(bzmail)

    def get(self, bug, date):
        pc = '{}::{}'.format(bug['product'], bug['component'])
        if pc not in self.data:
            mail = bug['triage_owner']
            nick = bug['triage_owner_detail']['nick']
            return mail, nick

        date = lmdutils.get_date_ymd(date)
        strategy = self.data[pc]
        dates = strategy['dates']
        i = bisect.bisect_left(strategy['dates'], date)
        if i == len(dates):
            bzmail = strategy['fallback']
        else:
            bzmail = strategy['mails'][i]
        nick = self.get_nick(bzmail)

        return bzmail, nick

    def get_who_to_nag(self, date):
        fallbacks = {}
        date = lmdutils.get_date_ymd(date)
        days = utils.get_config('round-robin', 'days_to_nag', 7)
        for pc, strategy in self.data.items():
            last_date = strategy['dates'][-1]
            if (last_date - date).days <= days and strategy[
                'filename'
            ] not in fallbacks:
                fallbacks[strategy['filename']] = strategy['fallback']

        # create a dict: mozmail -> list of filenames to check
        res = {}
        for fn, fb in fallbacks.items():
            if not self.is_mozilla(fb):
                raise BadFallback()
            mozmail = self.people.get_moz_mail(fb)
            if mozmail not in res:
                res[mozmail] = []
            res[mozmail].append(fn)

        res = {fb: sorted(fn) for fb, fn in res.items()}

        return res
