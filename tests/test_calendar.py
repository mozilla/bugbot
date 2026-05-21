# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.people import People
from bugbot.round_robin_calendar import ICSCalendar


def test_dom_lws_calendar():
    """Test the triage rotation calendar from DOM LWS team."""
    calendar = ICSCalendar.get(
        "tests/data/DOM_LWS_calendar.ics",
        "lws.fallback.triager@mozilla.tld",
        "DOM LWS",
        people=People([]),
    )

    assert calendar.get_persons("2023-03-11") == [("opettay", None)]
    assert calendar.get_persons("2023-03-25") == [("jstutte", None)]
    assert calendar.get_persons("2023-03-30") == [("krosylight", None)]


def test_performance_tools_calendar():
    """Test the triage rotation calendar from Performance Tools team."""
    calendar = ICSCalendar.get(
        "tests/data/Performance_Tools_calendar.ics",
        "performance.fallback.triager@mozilla.tld",
        "Performance Tools",
        people=People([]),
    )

    assert calendar.get_persons("2023-02-28") == [("Gregory Mierzwinski", None)]
    assert calendar.get_persons("2023-03-09") == [("Kash Shampur", None)]
    assert calendar.get_persons("2023-03-22") == [("Kash Shampur", None)]
    assert calendar.get_persons("2023-03-30") == [("Alexandru Ionescu", None)]
    assert calendar.get_persons("2023-04-20") == [("Andrej Glavic", None)]


def test_recurring_event():
    """Test a calendar with a recurring event."""
    calendar = ICSCalendar.get(
        "tests/data/calendar_recurring.ics",
        "recurring@mozilla.tld",
        "recurring",
        people=People([]),
    )

    assert calendar.get_persons("2022-12-01") == [("Gregory Mierzwinski", None)]
    assert calendar.get_persons("2023-02-28") == [("Gregory Mierzwinski", None)]
