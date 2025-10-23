# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os
import re
from bisect import bisect_left
from json.decoder import JSONDecodeError

import recurring_ical_events
import requests
from dateutil.parser import ParserError
from dateutil.relativedelta import relativedelta
from icalendar import Calendar as iCalendar
from libmozdata import utils as lmdutils

from bugbot import utils
from bugbot.people import People


class InvalidCalendar(Exception):
    pass


class BadFallback(Exception):
    pass


class InvalidDateError(ParserError):
    """Raised when a date in a rotation calendar is invalid"""


class Calendar:
    def __init__(self, fallback, team_name, people=None):
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
    def _convert_hg_to_github_url(url):
        """Convert hg.mozilla.org URLs to GitHub raw URLs
        
        Args:
            url: URL that may be an hg.mozilla.org URL
            
        Returns:
            Converted URL if it was an hg.mozilla.org URL, otherwise original URL
        """
        # Convert hg.mozilla.org URLs to GitHub URLs
        # From: https://hg.mozilla.org/mozilla-central/raw-file/tip/<path>
        # To: https://raw.githubusercontent.com/mozilla-firefox/firefox/main/<path>
        if url.startswith("https://hg.mozilla.org/mozilla-central/raw-file/tip/"):
            path = url.replace("https://hg.mozilla.org/mozilla-central/raw-file/tip/", "")
            return f"https://raw.githubusercontent.com/mozilla-firefox/firefox/main/{path}"
        return url

    @staticmethod
    def get(url, fallback, team_name, people=None):
        data = None
        if url.startswith("private://"):
            name = url.split("//", 1)[1]
            url = utils.get_private()[name]

        # Convert hg.mozilla.org URLs to GitHub URLs
        url = Calendar._convert_hg_to_github_url(url)

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
                return ICSCalendar(data, fallback, team_name, people=people)
            except ValueError:
                raise InvalidCalendar(
                    f"Cannot decode calendar: {url} for team {team_name}"
                )

    def __str__(self):
        return f"""Round robin calendar:
team name: {self.team_name}
fallback: {self.fallback}, bz: {self.fb_bzmail}, moz: {self.fb_mozmail}
team: {self.team}"""

    def __repr__(self):
        return self.__str__()


class JSONCalendar(Calendar):
    def __init__(self, cal, fallback, team_name, people=None):
        super().__init__(fallback, team_name, people=people)
        start_dates = cal.get("duty-start-dates", {})
        if start_dates:
            try:
                dates = sorted((lmdutils.get_date_ymd(d), d) for d in start_dates)
            except ParserError as err:
                raise InvalidDateError(
                    f"Invalid duty start date for the {team_name} team: {err}"
                ) from err
            self.set_team(
                list(start_dates[d] for _, d in dates), cal.get("triagers", {})
            )
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
            person = self.team[i][0]
        else:
            person = self.team[i - 1][0] if i != 0 else self.team[0][0]

        self.cache[date] = res = [(person, self.people.get_bzmail_from_name(person))]

        return res

    def guess_cycle(self):
        diffs = [(x - y).days for x, y in zip(self.dates[1:], self.dates[:-1])]
        mean = sum(diffs) / len(diffs)
        return int(round(mean))


class ICSCalendar(Calendar):
    # The summary can be "[Gfx Triage] Foo Bar" or just "Foo Bar"
    SUM_PAT = re.compile(r"\s*(?:\[[^\]]*\])?\s*(.*)")

    def __init__(self, cal, fallback, team_name, people=None):
        super().__init__(fallback, team_name, people=people)
        self.cal = iCalendar.from_ical(cal)

    def get_person(self, p):
        g = ICSCalendar.SUM_PAT.match(p)
        if g:
            p = g.group(1)
            p = p.strip()
        return p

    def get_persons(self, date):
        date = lmdutils.get_date_ymd(date)
        if date in self.cache:
            return self.cache[date]

        events = recurring_ical_events.of(self.cal).between(date, date)
        persons = [self.get_person(event["SUMMARY"]) for event in events]
        self.cache[date] = res = [
            (person, self.people.get_bzmail_from_name(person)) for person in persons
        ]

        return res
