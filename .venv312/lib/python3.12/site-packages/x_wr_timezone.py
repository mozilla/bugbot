# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""Bring calendars using X-WR-TIMEZONE into RFC 5545 form."""
import functools
from io import BytesIO
import sys
import zoneinfo
from icalendar.prop import vDDDTypes, vDDDLists
import datetime
import icalendar
from typing import Optional
import click

X_WR_TIMEZONE = "X-WR-TIMEZONE"


def list_is(l1, l2):
    """Return wether all contents of two lists are identical."""
    return len(l1) == len(l2) and all(e1 is e2 for e1, e2 in zip(l1, l2))


class CalendarWalker:
    """I walk along the components and values of an icalendar object.

    The idea is the same as a visitor pattern.
    """

    VALUE_ATTRIBUTES = ['DTSTART', 'DTEND', 'RDATE', 'RECURRENCE-ID', 'EXDATE']

    def copy_if_changed(self, component, attributes, subcomponents):
        """Check if an icalendar Component has changed and copy it if it has.

        atributes and subcomponents are put into the copy."""
        for key, value in attributes.items():
            if component[key] is not value:
                return self.copy_component(component, attributes, subcomponents)
        assert len(component.subcomponents) == len(subcomponents)
        for new_subcomponent, old_subcomponent in zip(subcomponents, component.subcomponents):
            if new_subcomponent is not old_subcomponent:
                return self.copy_component(component, attributes, subcomponents)
        return component

    def copy_component(self, component, attributes, subcomponents):
        """Create a copy of the component with attributes and subcomponents."""
        component = component.copy()
        for key, value in attributes.items():
            component[key] = value
        assert len(component.subcomponents) == 0
        for subcomponent in subcomponents:
             component.add_component(subcomponent)
        return component

    def walk(self, calendar):
        """Walk along the calendar and return the changed or identical object."""
        subcomponents = []
        for subcomponent in calendar.subcomponents:
            if isinstance(subcomponent, icalendar.cal.Event):
                subcomponent = self.walk_event(subcomponent)
            subcomponents.append(subcomponent)
        return self.copy_if_changed(calendar, {}, subcomponents)

    def walk_event(self, event):
        """Walk along the event and return the changed or identical object."""
        attributes = {}
        for name in self.VALUE_ATTRIBUTES:
            value = event.get(name)
            if value is not None:
                attributes[name] = self.walk_value(value)
        return self.copy_if_changed(event, attributes, event.subcomponents)

    def walk_value_default(self, value):
        """Default method for walking along a value type."""
        return value

    def walk_value(self, value):
        """Walk along a value type."""
        name = "walk_value_" + type(value).__name__
        walk = getattr(self, name, self.walk_value_default)
        return walk(value)

    def walk_value_list(self, l):
        """Walk through a list of values."""
        v = list(map(self.walk_value, l))
        if list_is(v, l):
            return l
        return v

    def walk_value_vDDDLists(self, l):
        dts = [ddd.dt for ddd in l.dts]
        new_dts = [self.walk_value(dt) for dt in dts]
        if list_is(new_dts, dts):
            return l
        return vDDDLists(new_dts)

    def walk_value_vDDDTypes(self, value):
        """Walk along an icalendar value type"""
        dt = self.walk_value(value.dt)
        if dt is value.dt:
            return value
        return vDDDTypes(dt)

    def walk_value_datetime(self, dt):
        """Walk along a datetime.datetime object."""
        return dt

    def is_UTC(self, dt):
        """Return whether the time zone is a UTC time zone."""
        if dt.tzname() is None:
            return False
        return dt.tzname().upper() == "UTC"

    def is_Floating(self, dt):
        return dt.tzname() is None


def is_pytz(tzinfo):
    """Whether the time zone requires localize() and normalize().

    pytz requires these funtions to be used in order to correctly use the
    time zones after operations.
    """
    return hasattr(tzinfo , "localize")


@functools.cache
def get_timezone_component(timezone:datetime.tzinfo) -> icalendar.Timezone:
    """Return a timezone component for the tzid and cache it.
    
    The result is cached.
    """
    return icalendar.Timezone.from_tzinfo(timezone)


class UTCChangingWalker(CalendarWalker):
    """Changes the UTC time zone into a new time zone."""

    def __init__(self, timezone):
        """Initialize the walker with the new time zone."""
        self.new_timezone = timezone

    def walk_value_datetime(self, dt):
        """Walk along a datetime.datetime object."""
        if self.is_UTC(dt):
            return dt.astimezone(self.new_timezone)
        elif self.is_Floating(dt):
            if is_pytz(self.new_timezone):
                return self.new_timezone.localize(dt)
            return dt.replace(tzinfo=self.new_timezone)
        return dt


def to_standard(
        calendar : icalendar.Calendar,
        timezone:Optional[datetime.tzinfo]=None,
        add_timezone_component:bool=False
    ) -> icalendar.Calendar:
    """Make a calendar that might use X-WR-TIMEZONE compatible with RFC 5545.

    Arguments:
    
        calendar: is an icalendar.Calendar object. It does not need to have
            the X-WR-TIMEZONE property but if it has, calendar  will be converted
            to conform to RFC 5545.
            
        timezone: an optional timezone argument if you want to override the
            existence of the actual X-WR-TIMEZONE property of the calendar.
            This can be a string like "Europe/Berlin" or "UTC" or a
            pytz.timezone or any other timezone accepted by the datetime module.
        
        add_timezone_component: whether to add a VTIMEZONE component to the result.
    """
    if timezone is None:
        timezone = calendar.get(X_WR_TIMEZONE, None)
    if timezone is not None and not isinstance(timezone, datetime.tzinfo):
        timezone = zoneinfo.ZoneInfo(str(timezone))
    result : icalendar.Calendar = calendar
    del calendar
    if timezone is not None:
        walker = UTCChangingWalker(timezone)
        result = walker.walk(result)
        if add_timezone_component:
            new_cal = result.copy()
            new_cal.subcomponents = result.subcomponents[:]
            result = new_cal
            result.subcomponents.insert(0, get_timezone_component(timezone))
    return result

@click.command()
@click.argument('in_file', type=click.File('rb'), default="-")
@click.argument('out_file', type=click.File('wb'), default="-")
@click.version_option()
@click.help_option()
@click.option('--add-timezone/--no-timezone', default=True, help="Add a VTIMEZONE component to the result.")
def main(in_file:BytesIO, out_file:BytesIO, add_timezone: bool):
    """x-wr-timezone converts ICSfiles with X-WR-TIMEZONE to use RFC 5545 instead.

    Convert input:

        cat in.ics | x-wr-timezone > out.ics
        wget -O- https://example.org/in.ics | x-wr-timezone > out.ics
        curl https://example.org/in.ics | x-wr-timezone > out.ics

    Convert files:

        x-wr-timezone in.ics out.ics

    By default, x-wr-timezone will add a VTIMEZONE component to the result.
    Use --no-vtimezone to remove it. (Added in v2.0.0)

    Get help:

        x-wr-timezone --help

    For bug reports, code and questions, visit the projet page:

        https://github.com/niccokunzmann/x-wr-timezone

    License: LPGLv3+
    """
    calendar = icalendar.Calendar.from_ical(in_file.read())
    new_cal = to_standard(calendar, add_timezone_component=add_timezone)
    out_file.write(new_cal.to_ical())
    return 0


__all__ = [
    "main", "to_standard", "UTCChangingWalker", "list_is",
    "X_WR_TIMEZONE", "CalendarWalker", "get_timezone_component",
]
