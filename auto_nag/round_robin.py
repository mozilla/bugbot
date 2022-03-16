# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
from random import randint

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import BugzillaUser

from auto_nag import logger, utils
from auto_nag.people import People
from auto_nag.round_robin_calendar import BadFallback, Calendar, InvalidCalendar


class RoundRobin(object):

    _instances = {}

    def __init__(self, rr=None, people=None, teams=None):
        self.people = People.get_instance() if people is None else people
        self.components_by_triager = {}
        self.all_calendars = []
        self.feed(teams, rr=rr)
        self.nicks = {}
        self.erroneous_bzmail = {}
        utils.init_random()

    @staticmethod
    def get_instance(teams=None):
        if teams is None:
            if None not in RoundRobin._instances:
                RoundRobin._instances[None] = RoundRobin()
            return RoundRobin._instances[None]

        teams = tuple(teams)
        if teams not in RoundRobin._instances:
            RoundRobin._instances[teams] = RoundRobin(teams=teams)
        return RoundRobin._instances[teams]

    def get_calendar(self, team, data):
        fallback = data["fallback"]
        strategies = set(data["components"].values())
        res = {}
        for strategy in strategies:
            url = data[strategy]["calendar"]
            res[strategy] = Calendar.get(url, fallback, team, people=self.people)
        return res

    def feed(self, teams, rr=None):
        self.data = {}
        filenames = {}
        if rr is None:
            rr = {}
            for team, path in utils.get_config(
                "round-robin", "teams", default={}
            ).items():
                if teams is not None and team not in teams:
                    continue
                with open("./auto_nag/scripts/configs/{}".format(path), "r") as In:
                    rr[team] = json.load(In)
                    filenames[team] = path

        # rr is dictionary:
        # - doc -> documentation
        # - components -> dictionary: Product::Component -> strategy name
        # - strategies: dictionary: {calendar: url}

        to_remove = []

        # Get all the strategies for each team
        for team, data in rr.items():
            try:
                calendars = self.get_calendar(team, data)
                self.all_calendars += list(calendars.values())

                # finally self.data is a dictionary:
                # - Product::Component -> dictionary {fallback: who to nag when we've nobody
                #                                     calendar}
                for pc, strategy in data["components"].items():
                    self.data[pc] = calendars[strategy]
            except (BadFallback, InvalidCalendar) as err:
                logger.error(err)
                to_remove.append(team)

        for team in to_remove:
            del rr[team]

    def get_components(self):
        return list(self.data.keys())

    def get_components_for_triager(self, triager):
        return self.components_by_triager[triager]

    def add_component_for_triager(self, component, triagers):
        if not isinstance(triagers, list):
            triagers = [triagers]
        for triager in triagers:
            if triager in self.components_by_triager:
                self.components_by_triager[triager].add(component)
            else:
                self.components_by_triager[triager] = {component}

    def get_fallback(self, bug):
        pc = bug["product"] + "::" + bug["component"]
        if pc not in self.data:
            mail = bug.get("triage_owner")
        else:
            cal = self.data[pc]
            mail = cal.get_fallback_bzmail()

        return self.people.get_moz_mail(mail)

    def get_erroneous_bzmail(self):
        return self.erroneous_bzmail

    def add_erroneous_bzmail(self, bzmail, prod_comp, cal):
        logger.error(f"No nick for {bzmail} for {prod_comp}")
        fb = cal.get_fallback_mozmail()
        if fb not in self.erroneous_bzmail:
            self.erroneous_bzmail[fb] = {bzmail}
        else:
            self.erroneous_bzmail[fb].add(bzmail)

    def get_nick(self, bzmail, prod_comp, cal):
        if bzmail not in self.nicks:

            def handler(user):
                self.nicks[bzmail] = user["nick"]

            BugzillaUser(
                user_names=[bzmail], 
                include_fields=["nick"], 
                user_handler=handler
            ).wait()

        if bzmail not in self.nicks:
            self.add_erroneous_bzmail(bzmail, prod_comp, cal)
            return None

        return self.nicks[bzmail]

    def get(self, bug, date, only_one=True, has_nick=True):
        pc = bug["product"] + "::" + bug["component"]
        if pc not in self.data:
            mail = bug.get("triage_owner")
            nick = bug.get("triage_owner_detail", {}).get("nick")
            if utils.is_no_assignee(mail):
                mail, nick = None, None

            if mail is None:
                logger.error("No triage owner for {}".format(pc))

            self.add_component_for_triager(pc, mail)

            if has_nick:
                return mail, nick if only_one else [(mail, nick)]
            return mail if only_one else [mail]

        cal = self.data[pc]
        persons = cal.get_persons(date)
        fb = cal.get_fallback_bzmail()
        if not persons or all(p is None for _, p in persons):
            # the fallback is the triage owner
            self.add_component_for_triager(pc, [fb])
            return (fb, self.get_nick(fb, pc, cal)) if has_nick else fb

        bzmails = []
        for _, p in persons:
            bzmails.append(fb if p is None else p)

        self.add_component_for_triager(pc, bzmails)

        if only_one:
            bzmail = bzmails[randint(0, len(bzmails) - 1)]
            if has_nick:
                nick = self.get_nick(bzmail, pc, cal)
                return bzmail, nick
            return bzmail

        if has_nick:
            return [(bzmail, self.get_nick(bzmail, pc, cal)) for bzmail in bzmails]
        return bzmails

    def get_who_to_nag(self, date):
        fallbacks = {}
        date = lmdutils.get_date_ymd(date)
        days = utils.get_config("round-robin", "days_to_nag", 7)
        next_date = date + relativedelta(days=days)
        for cal in self.all_calendars:
            persons = cal.get_persons(next_date)
            if persons and all(p is not None for _, p in persons):
                continue

            name = cal.get_team_name()
            fb = cal.get_fallback_mozmail()
            if fb not in fallbacks:
                fallbacks[fb] = {}
            if name not in fallbacks[fb]:
                fallbacks[fb][name] = {"nobody": False, "persons": []}
            info = fallbacks[fb][name]

            if not persons:
                info["nobody"] = True
            else:
                people_names = [n for n, p in persons if p is None]
                if people_names:
                    info["persons"] += people_names
        return fallbacks
