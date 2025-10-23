# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from bugbot.people import People
from bugbot.round_robin_calendar import Calendar, ICSCalendar


class TestICSCalendar(unittest.TestCase):
    """Test the ICSCalendar class."""

    def test_dom_lws_calendar(self):
        """Test the triage rotation calendar from DOM LWS team."""
        calendar = ICSCalendar.get(
            "tests/data/DOM_LWS_calendar.ics",
            "lws.fallback.triager@mozilla.tld",
            "DOM LWS",
            people=People([]),
        )

        self.assertEqual(calendar.get_persons("2023-03-11"), [("opettay", None)])
        self.assertEqual(calendar.get_persons("2023-03-25"), [("jstutte", None)])
        self.assertEqual(calendar.get_persons("2023-03-30"), [("krosylight", None)])

    def test_performance_tools_calendar(self):
        """Test the triage rotation calendar from Performance Tools team."""
        calendar = ICSCalendar.get(
            "tests/data/Performance_Tools_calendar.ics",
            "performance.fallback.triager@mozilla.tld",
            "Performance Tools",
            people=People([]),
        )

        self.assertEqual(
            calendar.get_persons("2023-02-28"), [("Gregory Mierzwinski", None)]
        )
        self.assertEqual(calendar.get_persons("2023-03-09"), [("Kash Shampur", None)])
        self.assertEqual(calendar.get_persons("2023-03-22"), [("Kash Shampur", None)])
        self.assertEqual(
            calendar.get_persons("2023-03-30"), [("Alexandru Ionescu", None)]
        )
        self.assertEqual(calendar.get_persons("2023-04-20"), [("Andrej Glavic", None)])

    def test_recurring_event(self):
        """Test a calendar with a recurring event."""
        calendar = ICSCalendar.get(
            "tests/data/calendar_recurring.ics",
            "recurring@mozilla.tld",
            "recurring",
            people=People([]),
        )

        self.assertEqual(
            calendar.get_persons("2022-12-01"), [("Gregory Mierzwinski", None)]
        )
        self.assertEqual(
            calendar.get_persons("2023-02-28"), [("Gregory Mierzwinski", None)]
        )


class TestCalendarURLConversion(unittest.TestCase):
    """Test the URL conversion from hg.mozilla.org to GitHub."""

    def test_convert_hg_to_github_url(self):
        """Test that hg.mozilla.org URLs are converted to GitHub URLs."""
        # Test conversion of hg.mozilla.org URL
        hg_url = "https://hg.mozilla.org/mozilla-central/raw-file/tip/browser/base/content/test/performance/triage.json"
        expected_github_url = "https://raw.githubusercontent.com/mozilla-firefox/firefox/main/browser/base/content/test/performance/triage.json"
        converted_url = Calendar._convert_hg_to_github_url(hg_url)
        self.assertEqual(converted_url, expected_github_url)

    def test_convert_hg_to_github_url_sessionstore(self):
        """Test conversion for sessionstore triage.json."""
        hg_url = "https://hg.mozilla.org/mozilla-central/raw-file/tip/browser/components/sessionstore/triage.json"
        expected_github_url = "https://raw.githubusercontent.com/mozilla-firefox/firefox/main/browser/components/sessionstore/triage.json"
        converted_url = Calendar._convert_hg_to_github_url(hg_url)
        self.assertEqual(converted_url, expected_github_url)

    def test_convert_hg_to_github_url_themes(self):
        """Test conversion for browser themes triage.json."""
        hg_url = "https://hg.mozilla.org/mozilla-central/raw-file/tip/browser/themes/triage.json"
        expected_github_url = "https://raw.githubusercontent.com/mozilla-firefox/firefox/main/browser/themes/triage.json"
        converted_url = Calendar._convert_hg_to_github_url(hg_url)
        self.assertEqual(converted_url, expected_github_url)

    def test_non_hg_url_unchanged(self):
        """Test that non-hg.mozilla.org URLs are not changed."""
        # Test that other URLs are not changed
        other_urls = [
            "https://example.com/calendar.json",
            "https://github.com/mozilla/bugbot/raw/main/calendar.json",
            "tests/data/calendar.json",
            "private://calendar",
        ]
        for url in other_urls:
            converted_url = Calendar._convert_hg_to_github_url(url)
            self.assertEqual(converted_url, url)
