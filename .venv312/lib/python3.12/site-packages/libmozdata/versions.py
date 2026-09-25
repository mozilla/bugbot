# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
from datetime import timedelta
from os.path import commonprefix

import requests
from icalendar import Calendar

from . import config, utils

__versions = None
__version_dates = None
__stability_version_dates = None


URL_VERSIONS = "https://product-details.mozilla.org/1.0/firefox_versions.json"
URL_HISTORY = (
    "https://product-details.mozilla.org/1.0/firefox_history_major_releases.json"
)
URL_CALENDAR = "https://www.google.com/calendar/ical/mozilla.com_2d37383433353432352d3939%40resource.calendar.google.com/public/basic.ics"
URL_STABILITY = (
    "https://product-details.mozilla.org/1.0/firefox_history_stability_releases.json"
)

REGEX_EVENT = re.compile("Firefox ([0-9]+) Release", re.IGNORECASE)


def __get_major(v):
    if not v:
        return
    return int(v.split(".")[0])


def __getVersions():
    """Get the versions number for each channel

    Returns:
        dict: versions for each channel
    """

    def _clean_esr(esr):
        if esr is None:
            return
        return esr.endswith("esr") and esr[:-3] or esr

    resp = requests.get(
        URL_VERSIONS,
        headers={"User-Agent": config.get("User-Agent", "name", required=True)},
    )
    data = resp.json()

    nightly = data["FIREFOX_NIGHTLY"]
    esr_next = _clean_esr(data["FIREFOX_ESR_NEXT"])
    esr = _clean_esr(data["FIREFOX_ESR"])

    return {
        "release": data["LATEST_FIREFOX_VERSION"],
        "beta": data["LATEST_FIREFOX_RELEASED_DEVEL_VERSION"],
        "nightly": nightly,
        "esr": esr_next or esr,
        "esr_previous": esr_next is not None and esr or None,
    }


def __getVersionDates():
    resp = requests.get(
        URL_HISTORY,
        headers={"User-Agent": config.get("User-Agent", "name", required=True)},
    )
    data = resp.json()

    data = dict([(v, utils.get_moz_date(d)) for v, d in data.items()])

    resp = requests.get(
        URL_CALENDAR,
        headers={"User-Agent": config.get("User-Agent", "name", required=True)},
    )
    calendar = Calendar.from_ical(resp.content)

    for component in calendar.walk():
        if component.name == "VEVENT":
            match = REGEX_EVENT.search(component.get("summary"))
            if match:
                version = match.group(1) + ".0"
                if version not in data:
                    data[version] = utils.get_moz_date(
                        utils.get_date_str(component.decoded("dtstart"))
                    )

    return data


def __getStabilityVersionDates():
    resp = requests.get(
        URL_STABILITY,
        headers={"User-Agent": config.get("User-Agent", "name", required=True)},
    )

    return dict([(v, utils.get_moz_date(d)) for v, d in resp.json().items()])


def get(base=False):
    """Get current version number by channel

    Returns:
        dict: containing version by channel
    """
    global __versions
    if not __versions:
        __versions = __getVersions()

    if base:
        res = {}
        for k, v in __versions.items():
            res[k] = __get_major(v)
        return res

    return __versions


def __getMatchingVersion(version, versions_dates):
    date = None
    longest_match = []
    longest_match_v = None
    for v, d in versions_dates:
        match = commonprefix([v.split("."), str(version).split(".")])
        if len(match) > 0 and (
            len(match) > len(longest_match)
            or (
                len(match) == len(longest_match)
                and int(v[-1]) <= int(longest_match_v[-1])
            )
        ):
            longest_match = match
            longest_match_v = v
            date = d

    return date


def getMajorDate(version):
    global __version_dates
    if not __version_dates:
        __version_dates = __getVersionDates()

    return __getMatchingVersion(version, __version_dates.items())


def getDate(version):
    global __version_dates, __stability_version_dates
    if not __version_dates:
        __version_dates = __getVersionDates()
    if not __stability_version_dates:
        __stability_version_dates = __getStabilityVersionDates()

    return __getMatchingVersion(
        version, list(__version_dates.items()) + list(__stability_version_dates.items())
    )


def __getCloserDate(date, versions_dates, negative=False):
    def diff(d):
        return d - date

    future_dates = [
        (v, d) for v, d in versions_dates if negative or diff(d) > timedelta(0)
    ]
    if not future_dates:
        raise Exception("No future release found")
    return min(future_dates, key=lambda i: abs(diff(i[1])))


def getCloserMajorRelease(date, negative=False):
    global __version_dates
    if not __version_dates:
        __version_dates = __getVersionDates()

    return __getCloserDate(date, __version_dates.items(), negative)


def getCloserRelease(date, negative=False):
    global __version_dates, __stability_version_dates
    if not __version_dates:
        __version_dates = __getVersionDates()
    if not __stability_version_dates:
        __stability_version_dates = __getStabilityVersionDates()

    return __getCloserDate(
        date,
        list(__version_dates.items()) + list(__stability_version_dates.items()),
        negative,
    )
