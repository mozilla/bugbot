# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import calendar
import math
import operator
import os.path
import random
from datetime import date, datetime, timedelta, timezone
from itertools import count

import dateutil.parser
import pytz
import six
from dateutil.relativedelta import relativedelta
from requests.utils import quote

__pacific = pytz.timezone("US/Pacific")


def get_best(stats):
    """Get the key which has the higher value

    Args:
        stats (dict): the stats contained in a dictionary

    Returns:
        a key
    """
    if stats:
        return max(stats.items(), key=operator.itemgetter(1))[0]
    else:
        return None


def get_timestamp(dt):
    """Get a timestamp from a date

    Args:
        dt: a string or a datetime object

    Returns:
        int: the corresponding timestamp
    """
    if isinstance(dt, six.string_types):
        dt = datetime.now(timezone.utc) if dt == "now" else get_date_ymd(dt)
    return int(calendar.timegm(dt.timetuple()))


def get_date_from_timestamp(ts):
    """Get a UTC date from a timestamp

    Args:
        ts(int): a timestamp

    Returns:
        datetime.datetime: the corresponding datetime in UTC tz
    """
    return datetime.fromtimestamp(ts, tz=pytz.utc)


def get_date_ymd(dt):
    """Get a datetime from a string 'Year-month-day'

    Args:
        dt (str): a date

    Returns:
        datetime: a datetime object
    """
    assert dt

    if isinstance(dt, datetime):
        return as_utc(dt)

    if dt == "today":
        today = datetime.now(timezone.utc)
        return pytz.utc.localize(datetime(today.year, today.month, today.day))
    elif dt == "tomorrow":
        tomorrow = datetime.now(timezone.utc) + timedelta(1)
        return pytz.utc.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day))
    elif dt == "yesterday":
        yesterday = datetime.now(timezone.utc) - timedelta(1)
        return pytz.utc.localize(
            datetime(yesterday.year, yesterday.month, yesterday.day)
        )

    return as_utc(dateutil.parser.parse(dt))


def get_today():
    """Get the date for today

    Returns:
        str: the date of today
    """
    return get_date_str(date.today())


def get_date_str(ymd):
    """Get the date as string

    Args:
        ymd (datetime): a datetime
    Returns:
        str: the date as a string 'Year-month-day'
    """
    return ymd.strftime("%Y-%m-%d")


def get_date(_date, delta=None):
    """Get the date as string

    Args:
        ymd (str): a date
        delta (int): the number of days to remove
    Returns:
        str: the date as a string 'Year-month-day'
    """
    if isinstance(_date, six.string_types):
        _date = get_date_ymd(_date)
    if delta:
        _date -= timedelta(delta)
    return get_date_str(_date)


def get_now_timestamp():
    """Get timestamp for now

    Returns:
        int: timestamp for now
    """
    return get_timestamp(datetime.now(timezone.utc))


def is64(cpu_name):
    """Check if a cpu is 64 bits or not

    Args:
        cpu_name (str): the cpu name

    Returns:
        bool: True if 64 is in the name
    """
    return "64" in cpu_name


def percent(x):
    """Get a percent from a ratio (0.23 => 23%)

    Args:
        x (float): ratio

    Returns:
        str: a string with a percent
    """
    return simple_percent(round(100 * x, 1))


def simple_percent(x):
    """Get a percent string

    Args:
        x (float): number

    Returns:
        str: a string with a percent
    """
    if math.floor(x) == x:
        x = int(x)
    return str(x) + "%"


def get_sample(data, fraction):
    """Get a random sample from the data according to the fraction

    Args:
        data (list): data
        fraction (float): the fraction

    Returns:
        list: a random sample
    """
    if fraction < 0 or fraction >= 1:
        return data
    else:
        return random.sample(data, int(fraction * len(data)))


def get_date_from_buildid(bid):
    """Get a date from buildid

    Args:
        bid (str): build_id

    Returns:
        date: date object
    """
    # 20160407164938 == 2016 04 07 16 49 38
    bid = str(bid)
    year = int(bid[:4])
    month = int(bid[4:6])
    day = int(bid[6:8])
    hour = int(bid[8:10])
    minute = int(bid[10:12])
    second = int(bid[12:14])

    return __pacific.localize(
        datetime(year, month, day, hour, minute, second)
    ).astimezone(pytz.utc)


def get_buildid_from_date(d):
    """Get a buildid from a date

    Args:
        d (datetime.datetime): the date

    Returns:
        str: the build_id
    """
    return d.astimezone(__pacific).strftime("%Y%m%d%H%M%S")


def as_utc(d):
    """Convert a date in UTC

    Args:
        d (datetime.datetime): the date

    Returns:
        datetime.datetime: the localized date
    """
    if isinstance(d, datetime):
        if d.tzinfo is None or d.tzinfo.utcoffset(d) is None:
            return pytz.utc.localize(d)
        return d.astimezone(pytz.utc)
    elif isinstance(d, date):
        return pytz.utc.localize(datetime(d.year, d.month, d.day))


def get_moz_date(d):
    """Convert a Mozilla date in UTC

    Args:
        d (str): the date

    Returns:
        datetime.datetime: the localized date
    """
    return (
        pytz.timezone("US/Pacific")
        .localize(dateutil.parser.parse(d))
        .astimezone(pytz.utc)
    )


def rate(x, y):
    """Compute a rate

    Args:
        x (num): numerator
        y (num): denominator

    Returns:
        float: x / y or Nan if y == 0
    """
    return float(x) / float(y) if y else float("nan")


def get_guttenberg_death():
    return get_date_ymd("1468-02-03T00:00:00Z")


def signatures_parser(signatures):
    _set = set()
    if signatures:
        signatures = map(lambda s: s.strip(" \t\r\n"), signatures.split("[@"))
        signatures = map(lambda s: s[:-1].strip(" \t\r\n"), filter(None, signatures))
        for s in filter(None, signatures):
            _set.add(s)
    return list(_set)


def get_monday_sunday(date):
    iso = date.isocalendar()
    delta_monday = iso[2] - 1
    delta_sunday = 7 - iso[2]
    return (
        date - relativedelta(days=delta_monday),
        date + relativedelta(days=delta_sunday),
    )


def mean_stddev(x):
    N = len(x)
    m = sum(x) / N
    v = sum([xi**2 for xi in x]) / N - m**2
    e = math.sqrt(v)

    return m, e


def get_channels():
    return ["nightly", "aurora", "beta", "release", "esr"]


def get_str_list(x):
    if isinstance(x, six.string_types):
        return [x]
    if isinstance(x, six.integer_types):
        return [str[x]]
    if isinstance(x, list) or isinstance(x, set):
        return [str(y) if isinstance(y, six.integer_types) else y for y in x]


def get_x_fwed_for_str(s):
    if isinstance(s, six.string_types):
        return ", ".join(map(lambda x: x.strip(" \t"), s.split(",")))
    else:
        return ", ".join(map(lambda x: x.strip(" \t"), s))


def get_params_for_url(params):
    return (
        "?"
        + "&".join(
            [
                (
                    quote(name) + "=" + quote(str(value))
                    if not isinstance(value, list)
                    else "&".join(
                        [quote(name) + "=" + quote(str(intValue)) for intValue in value]
                    )
                )
                for name, value in sorted(params.items(), key=lambda p: p[0])
                if value is not None
            ]
        )
        if params
        else ""
    )


def get_url(url):
    return url if url.endswith("/") else url + "/"


def get_language(path):
    """
    Detect programming language or tool
    from a filename
    """
    name = os.path.basename(path)
    extension = os.path.splitext(name)[1][1:]
    langs = {
        "Shell": ["sh"],
        "Xml": ["xml", "xst"],
        "Html": ["html", "xhtml"],
        "Css": ["css"],
        "Javascript": ["js", "jsm"],
        "Makefile": [
            "mk",
            "Makefile",
            "Makefile.am",
            "Makefile.in",
            "configure.in",
            "autoconf.mk.in",
        ],
        "C++": ["cpp", "hpp", "hh"],
        "C": ["c", "h"],
        "Java": ["java"],
        "Font": ["ttf", "ttf^headers^"],
        "Tests": ["reftest.list", "crashtests.list"],
        "Windows IDL": ["idl"],
        "Mozilla XUL": ["xul"],
        "Ini": ["ini"],
        "License": ["LICENSE"],
        "Python": ["py"],
        "moz.build": ["moz.build"],
        "Rust": ["rs"],
    }
    for lang, names in langs.items():
        if name in names or extension in names:
            return lang


# This is roughly equivalent to the itertools.islice which was added in
# Python 3.10.
# Copied from https://docs.python.org/3/library/itertools.html#itertools.islice
def islice(iterable, *args):
    # islice('ABCDEFG', 2) → A B
    # islice('ABCDEFG', 2, 4) → C D
    # islice('ABCDEFG', 2, None) → C D E F G
    # islice('ABCDEFG', 0, None, 2) → A C E G

    s = slice(*args)
    start = 0 if s.start is None else s.start
    stop = s.stop
    step = 1 if s.step is None else s.step
    if start < 0 or (stop is not None and stop < 0) or step <= 0:
        raise ValueError

    indices = count() if stop is None else range(max(start, stop))
    next_i = start
    for i, element in zip(indices, iterable):
        if i == next_i:
            yield element
            next_i += step


# This is roughly equivalent to the itertools.batched which was added in
# Python 3.12.
# Copied from https://docs.python.org/3/library/itertools.html#itertools.batched
def batched(iterable, n):
    # batched('ABCDEFG', 3) → ABC DEF G
    if n < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(islice(iterator, n)):
        yield batch
