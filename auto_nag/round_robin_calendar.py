# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bisect import bisect_left
from dateutil.relativedelta import relativedelta
from icalevents.icalparser import parse_events
import json

try:
    from json.decoder import JSONDecodeError
except:  # NOQA
    JSONDecodeError = ValueError
from libmozdata import utils as lmdutils
import os
import re
import requests
from auto_nag.people import People
from auto_nag import utils


class InvalidCalendar(Exception):
    pass


class BadFallback(Exception):
    pass


class Calendar(object):
    def __init__(self, cal, fallback, team_name, people=None):
        super(Calendar, self).__init__()
        self.cal = cal
        self.people = People() if people is None else people
        self.fallback = fallback
        self.fb_bzmail = self.people.get_bzmail_from_name(self.fallback)
        self.fb_mozmail = self.people.get_moz_mail(self.fb_bzmail)
        self.team_name = team_name
        self.cache = {}

    def get_fallback(self):
        return self.fallback

    def get_fallback_bzmail(self):
        if not self.fb_bzmail:
            raise BadFallback('\'{}\' is an invalid fallback'.format(self.fallback))
        return self.fb_bzmail

    def get_fallback_mozmail(self):
        if not self.fb_mozmail:
            raise BadFallback('\'{}\' is an invalid fallback'.format(self.fallback))
        return self.fb_mozmail

    def get_team_name(self):
        return self.team_name

    def get_persons(self, date):
        return []

    def set_team(self, team, triagers):
        self.team = []
        for p in team:
            if p in triagers and 'bzmail' in triagers[p]:
                bzmail = triagers[p]['bzmail']
            else:
                bzmail = self.people.get_bzmail_from_name(p)
            self.team.append((p, bzmail))

    @staticmethod
    def get(url, fallback, team_name, people=None):
        data = None
        if url.startswith('private://'):
            name = url.split('//', 1)[1]
            url = utils.get_private()[name]

        if url.startswith('http'):
            r = requests.get(url)
            data = r.text
        elif os.path.isfile(url):
            with open(url, 'r') as In:
                data = In.read()
        else:
            data = url

        if data is None:
            raise InvalidCalendar('Cannot read calendar: {}'.format(url))

        try:
            cal = json.loads(data)
            return JSONCalendar(cal, fallback, team_name, people=people)
        except JSONDecodeError:
            try:
                # there is an issue with dateutil.rrule parser when until doesn't have a tz
                # so a workaround is to add a Z at the end of the string.
                pat = re.compile(r'^RRULE:(.*)UNTIL=([0-9Z]+)', re.MULTILINE | re.I)

                def sub(m):
                    date = m.group(1)
                    if date.lower().endswith('z'):
                        return date
                    return date + 'Z'

                data = pat.sub(sub, data)

                return ICSCalendar(data, fallback, team_name, people=people)
            except ValueError:
                raise InvalidCalendar('Cannot decode calendar: {}'.format(url))


class JSONCalendar(Calendar):
    def __init__(self, cal, fallback, team_name, people=None):
        super(JSONCalendar, self).__init__(
            cal['duty-start-dates'], fallback, team_name, people=people
        )
        dates = sorted((lmdutils.get_date_ymd(d), d) for d in self.cal.keys())
        self.set_team(list(self.cal[d] for _, d in dates), cal.get('triagers', {}))
        self.dates = [d for d, _ in dates]
        cycle = self.guess_cycle()
        self.dates.append(self.dates[-1] + relativedelta(days=cycle))
        self.team.append(None)

    def get_persons(self, date):
        date = lmdutils.get_date_ymd(date)
        if date in self.cache:
            return self.cache[date]

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
    def __init__(self, cal, fallback, team_name, people=None):
        super(ICSCalendar, self).__init__(cal, fallback, team_name, people=people)

    def get_persons(self, date):
        date = lmdutils.get_date_ymd(date)
        if date in self.cache:
            return self.cache[date]

        res = parse_events(self.cal, start=date, end=date)
        self.cache[date] = res = [
            (p.summary, self.people.get_bzmail_from_name(p.summary)) for p in res
        ]

        return res
