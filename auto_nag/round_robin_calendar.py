# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os
import re
from bisect import bisect_left
from json.decoder import JSONDecodeError

import requests
from dateutil.relativedelta import relativedelta
from dateutil.tz import UTC, gettz
from icalendar import Calendar as iCalendar
from icalevents.icalparser import parse_events
from libmozdata import utils as lmdutils

from auto_nag import utils
from auto_nag.people import People


class InvalidCalendar(Exception):
    pass


class BadFallback(Exception):
    pass


class Calendar(object):
    def __init__(self, cal, fallback, team_name, people=None):
        super(Calendar, self).__init__()
        self.cal = cal
        self.people = People.get_instance() if people is None else people
        self.fallback = fallback
        self.fb_bzmail = self.people.get_bzmail_from_name(self.fallback)
        self.fb_mozmail = self.people.get_moz_mail(self.fb_bzmail)
        self.team_name = team_name
        self.team = []
        self.cache = {}

    def get_fallback(self):
        return self.fallback

    def get_fallback_bzmail(self):
        if not self.fb_bzmail:
            raise BadFallback("'{}' is an invalid fallback".format(self.fallback))
        return self.fb_bzmail

    def get_fallback_mozmail(self):
        if not self.fb_mozmail:
            raise BadFallback("'{}' is an invalid fallback".format(self.fallback))
        return self.fb_mozmail

    def get_team_name(self):
        return self.team_name

    def get_persons(self, date):
        return []

    def set_team(self, team, triagers):
        for p in team:
            if p in triagers and "bzmail" in triagers[p]:
                bzmail = triagers[p]["bzmail"]
            else:
                bzmail = self.people.get_bzmail_from_name(p)
            self.team.append((p, bzmail))

    @staticmethod
    def get(url, fallback, team_name, people=None):
        data = None
        if url.startswith("private://"):
            name = url.split("//", 1)[1]
            url = utils.get_private()[name]

        if url.startswith("http"):
            r = requests.get(url)
            data = r.text
        elif os.path.isfile(url):
            with open(url, "r") as In:
                data = In.read()
        else:
            data = url

        if data is None:
            raise InvalidCalendar("Cannot read calendar: {}".format(url))

        try:
            cal = json.loads(data)
            return JSONCalendar(cal, fallback, team_name, people=people)
        except JSONDecodeError:
            try:
                # there is an issue with dateutil.rrule parser when until doesn't have a tz
                # so a workaround is to add a Z at the end of the string.
                pat = re.compile(r"^RRULE:(.*)UNTIL=([0-9Z]+)", re.MULTILINE | re.I)

                def sub(m):
                    date = m.group(1)
                    if date.lower().endswith("z"):
                        return date
                    return date + "Z"

                data = pat.sub(sub, data)

                return ICSCalendar(data, fallback, team_name, people=people)
            except ValueError:
                raise InvalidCalendar("Cannot decode calendar: {}".format(url))

    def __str__(self):
        return f"""Round robin calendar:
team name: {self.team_name}
fallback: {self.fallback}, bz: {self.fb_bzmail}, moz: {self.fb_mozmail}
team: {self.team}"""

    def __repr__(self):
        return self.__str__()


class JSONCalendar(Calendar):
    def __init__(self, cal, fallback, team_name, people=None):
        super(JSONCalendar, self).__init__(
            cal.get("duty-start-dates", {}), fallback, team_name, people=people
        )
        if self.cal:
            dates = sorted((lmdutils.get_date_ymd(d), d) for d in self.cal.keys())
            self.set_team(list(self.cal[d] for _, d in dates), cal.get("triagers", {}))
            self.dates = [d for d, _ in dates]
            cycle = self.guess_cycle()
            self.dates.append(self.dates[-1] + relativedelta(days=cycle))
            self.team.append(None)
        else:
            triagers = cal["triagers"]
            self.set_team(triagers.keys(), triagers)
            self.dates = []

    def get_persons(self, date):
        date = lmdutils.get_date_ymd(date)
        if date in self.cache:
            return self.cache[date]

        if not self.dates:
            # no dates so only triagers
            return self.team

        i = bisect_left(self.dates, date)
        if i == len(self.dates):
            self.cache[date] = []
            return []

        if date == self.dates[i]:
            person = self.team[i]
        else:
            person = self.team[i - 1] if i != 0 else self.team[0]

        self.cache[date] = [person]

        return [person]

    def guess_cycle(self):
        diffs = [(x - y).days for x, y in zip(self.dates[1:], self.dates[:-1])]
        mean = sum(diffs) / len(diffs)
        return int(round(mean))


class ICSCalendar(Calendar):

    # The summary can be "[Gfx Triage] Foo Bar" or just "Foo Bar"
    SUM_PAT = re.compile(r"\s*(?:\[[^\]]*\])?\s*(.*)")

    def __init__(self, cal, fallback, team_name, people=None):
        super(ICSCalendar, self).__init__(cal, fallback, team_name, people=people)
        self.set_tz()

    def set_tz(self):
        cal = iCalendar.from_ical(self.cal)
        for c in cal.walk():
            if c.name == "VTIMEZONE":
                self.cal_tz = gettz(str(c["TZID"]))
                break
        else:
            self.cal_tz = UTC

    def get_person(self, p):
        g = ICSCalendar.SUM_PAT.match(p)
        if g:
            p = g.group(1)
            p = p.strip()
        return p

    def get_persons(self, date):
        date = lmdutils.get_date_ymd(date)
        date += relativedelta(seconds=1)
        date = date.replace(tzinfo=self.cal_tz)
        if date in self.cache:
            return self.cache[date]

        res = parse_events(self.cal, start=date, end=date)
        persons = [self.get_person(p.summary) for p in res]
        self.cache[date] = res = [
            (person, self.people.get_bzmail_from_name(person)) for person in persons
        ]

        return res
