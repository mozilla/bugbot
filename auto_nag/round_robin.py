# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import csv
from typing import Dict, Iterator, Set

import requests
from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import BugzillaUser
from tenacity import (
    retry,
    retry_if_exception_message,
    stop_after_attempt,
    wait_exponential,
)

from auto_nag import logger, utils
from auto_nag.components import Components
from auto_nag.people import People
from auto_nag.round_robin_calendar import BadFallback, Calendar, InvalidCalendar


class RoundRobin(object):

    _instances: dict = {}

    def __init__(self, rotation_definitions=None, people=None, teams=None, days_to_nag: int = 7):
        self.people = People.get_instance() if people is None else people
        self.components_by_triager: Dict[str, list] = {}
        self.rotation_definitions = (
            RotationDefinitions()
            if rotation_definitions is None
            else rotation_definitions
        )
        self.feed(None if teams is None else set(teams))
        self.nicks = {}
        self.erroneous_bzmail = {}
        utils.init_random()

    @staticmethod
    def get_instance(teams=None):
        if teams is None:
            if None not in RoundRobin._instances:
                RoundRobin._instances[None] = RoundRobin()
            return RoundRobin._instances[None]

        teams = tuple(sorted(teams))
        if teams not in RoundRobin._instances:
            RoundRobin._instances[teams] = RoundRobin(teams=teams)
        return RoundRobin._instances[teams]

    def feed(self, teams: Set[str] = None) -> None:
        """Fetch the rotations calendars.

        Args:
            teams: if provided, only calendars for the specified teams will be
                fetched.
        """

        self.data = {}
        cache = {}

        team_calendars = self.rotation_definitions.fetch_by_teams()
        for team_name, components in team_calendars.items():
            if teams is not None and team_name not in teams:
                continue
            try:
                for component_name, calendar_info in components.items():
                    url = calendar_info["url"]
                    if url not in cache:
                        calendar = cache[url] = Calendar.get(
                            url,
                            calendar_info["fallback"],
                            team_name,
                            people=self.people,
                        )
                    else:
                        calendar = cache[url]
                        if calendar.get_fallback() != calendar_info["fallback"]:
                            raise BadFallback(
                                "Cannot have different fallback triagers for the same calendar"
                            )

                    self.data[component_name] = calendar

            except (BadFallback, InvalidCalendar) as err:
                logger.error(err)
                # If one the team's calendars failed, it is better to fail loud,
                # and disable all team's calendars.
                for component_name in components:
                    if component_name in self.data:
                        del self.data[component_name]

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

            BugzillaUser(user_names=[bzmail], user_handler=handler).wait()

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
            bzmail = bzmails[0]
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
        for cal in set(self.data.values()):
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


CalendarDef = Dict[str, str]
ComponentCalendarDefs = Dict[str, CalendarDef]
TeamCalendarDefs = Dict[str, ComponentCalendarDefs]


class RotationDefinitions:
    """Definitions for triage owner rotations"""

    def __init__(self) -> None:
        self.definitions_url = utils.get_private()["round_robin_sheet"]
        self.components = Components.get_instance()

    def fetch_by_teams(self) -> TeamCalendarDefs:
        """Fetch the triage owner rotation definitions and group them by team

        Returns:
            A dictionary that maps each component to its calendar and fallback
            person. The components are grouped by their teams. The following is
            the shape of the returned dictionary:
            {
                team_name: {
                    component_name:{
                            "fallback": "the name of the fallback person",
                            "calendar": "the URL for the rotation calendar"
                    }
                    ...
                }
                ...
            }
        """

        teams: TeamCalendarDefs = {}
        seen = set()
        for row in csv.DictReader(self.get_definitions_csv_lines()):
            team_name = row["Team Name"]
            scope = row["Calendar Scope"]
            fallback_triager = row["Fallback Triager"]
            calendar_url = row["Calendar URL"]

            if (team_name, scope) in seen:
                logger.error(
                    "The triage owner rotation definitions show more than one "
                    "entry for the %s team with the component scope '%s'",
                    team_name,
                    scope,
                )
            else:
                seen.add((team_name, scope))

            if team_name in teams:
                component_calendar = teams[team_name]
            else:
                component_calendar = teams[team_name] = {}

            if scope == "All Team's Components":
                team_components = self.components.get_team_components(team_name)
                components_to_add = [
                    str(component_name)
                    for component_name in team_components
                    if str(component_name) not in component_calendar
                ]
            else:
                components_to_add = [scope]

            for component_name in components_to_add:
                component_calendar[component_name] = {
                    "fallback": fallback_triager,
                    "url": calendar_url,
                }

        return teams

    def get_definitions_csv_lines(self) -> Iterator[str]:
        """Get the definitions for the triage owner rotations in CSV format.

        Returns:
            An iterator where each iteration should return a line from the CSV
            file. The first line will be the headers::
                - Team Name
                - Calendar Scope
                - Fallback Triager
                - Calendar URL"
        """
        return self._fetch_definitions_csv()

    @retry(
        retry=retry_if_exception_message(match=r"^\d{3} Server Error"),
        wait=wait_exponential(min=4),
        stop=stop_after_attempt(3),
    )
    def _fetch_definitions_csv(self) -> Iterator[str]:
        resp = requests.get(self.definitions_url)
        resp.raise_for_status()

        return resp.iter_lines(decode_unicode=True)
