# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import bisect
import json
from libmozdata import utils as lmdutils

from auto_nag import utils


class RoundRobin(object):
    def __init__(self, rr=None):
        self.feed(rr=rr)

    def feed(self, rr=None):
        self.data = {}
        if rr is None:
            rr = {}
            for team, path in utils.get_config(
                'round-robin', "teams", default={}
            ).items():
                with open('./auto_nag/scripts/configs/{}'.format(path), 'r') as In:
                    rr[team] = json.load(In)

        # rr is dictionary:
        # - doc -> documentation
        # - triagers -> dictionary: Real Name -> {bzmail: bugzilla email, nick: bugzilla nickname}
        # - components -> dictionary: Product::Compoent -> strategy name
        # - strategies: dictionay: {duty en date -> Real Name}

        # Get all the strategies for each team
        for team, data in rr.items():
            if 'doc' in data:
                del data['doc']
            strategies = {}
            triagers = data['triagers']
            fallback = triagers['Fallback']['bzmail']
            fallback_nick = triagers['Fallback']['nick']

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
                    # collect the tuple (end_date, bzmail, nick)
                    date = lmdutils.get_date_ymd(date)
                    bzmail = triagers[name]['bzmail']
                    nick = triagers[name]['nick']
                    date_name.append((date, bzmail, nick))

                # we sort the list to use bisection to find the triager
                date_name = sorted(date_name)
                strategies[strat_name] = {
                    'dates': [d for d, _, _ in date_name],
                    'mails': [(m, n) for _, m, n in date_name],
                    'fallback': (fallback, fallback_nick),
                }

            # finally self.data is a dictionary:
            # - Product::Component -> dictionary {dates: sorted list of end date
            #                                     mails: list of tuple (mail, nick)
            #                                     fallback: who to nag when we've nobody}
            for pc, strategy in data['components'].items():
                self.data[pc] = strategies[strategy]

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
            bzmail, nick = strategy['fallback']
        else:
            bzmail, nick = strategy['mails'][i]
        return bzmail, nick
