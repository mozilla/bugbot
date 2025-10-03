# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import datetime
import json
import os
import random
import re
from typing import Iterable, Union
from urllib.parse import quote_plus, urlencode

import dateutil.parser
import humanize
import pytz
import requests
from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from libmozdata import versions as lmdversions
from libmozdata.bugzilla import Bugzilla, BugzillaShorten
from libmozdata.fx_trains import FirefoxTrains
from libmozdata.hgmozilla import Mercurial
from requests.exceptions import HTTPError

from bugbot.constants import (
    BOT_MAIN_ACCOUNT,
    HIGH_PRIORITY,
    HIGH_SEVERITY,
    OLD_SEVERITY_MAP,
)

_CONFIG = None
_CYCLE_SPAN = None
_MERGE_DAY = None
_TRIAGE_OWNERS = None
_DEFAULT_ASSIGNEES = None
_CURRENT_VERSIONS = None
_CONFIG_PATH = "./configs/"


BZ_FIELD_PAT = re.compile(r"^[fovj]([0-9]+)$")
PAR_PAT = re.compile(r"\([^\)]*\)")
BRA_PAT = re.compile(r"\[[^\]]*\]")
DIA_PAT = re.compile("<[^>]*>")
UTC_PAT = re.compile(r"UTC\+[^ \t]*")
COL_PAT = re.compile(":[^:]*")
BACKOUT_PAT = re.compile("^back(s|(ed))?[ \t]*out", re.I)
BUG_PAT = re.compile(r"^bug[s]?[ \t]*([0-9]+)", re.I)
WHITEBOARD_ACCESS_PAT = re.compile(r"\[access\-s\d\]")

MAX_URL_LENGTH = 512


def get_weekdays():
    return {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


def _get_config():
    global _CONFIG
    if _CONFIG is None:
        try:
            with open(_CONFIG_PATH + "/rules.json", "r") as In:
                _CONFIG = json.load(In)
        except IOError:
            _CONFIG = {}
    return _CONFIG


def get_config(name, entry, default=None):
    conf = _get_config()
    if name not in conf:
        name = "common"
    rule_conf = conf[name]
    if entry in rule_conf:
        return rule_conf[entry]
    rule_conf = conf["common"]
    return rule_conf.get(entry, default)


def get_receivers(rule_name):
    receiver_lists = get_config("common", "receiver_list", default={})

    receivers = get_config(rule_name, "receivers", [])
    if isinstance(receivers, str):
        receivers = receiver_lists[receivers]

    additional_receivers = get_config(rule_name, "additional_receivers", [])
    if isinstance(additional_receivers, str):
        additional_receivers = receiver_lists[additional_receivers]

    return list(dict.fromkeys([*receivers, *additional_receivers]))


def init_random():
    now = datetime.datetime.utcnow()
    now = now.timestamp()
    random.seed(now)


def get_signatures(sgns):
    if not sgns:
        return set()

    res = set()
    sgns = map(lambda x: x.strip(), sgns.split("[@"))
    for s in filter(None, sgns):
        try:
            i = s.rindex("]")
            res.add(s[:i].strip())
        except ValueError:
            res.add(s)
    return res


def add_signatures(old, new):
    added_sgns = "[@ " + "]\n[@ ".join(sorted(new)) + "]"
    if old:
        return old + "\n" + added_sgns
    return added_sgns


def get_empty_assignees(params, negation=False):
    n = get_last_field_num(params)
    n = int(n)
    params.update(
        {
            "j" + str(n): "OR",
            "f" + str(n): "OP",
            "f" + str(n + 1): "assigned_to",
            "o" + str(n + 1): "equals",
            "v" + str(n + 1): "nobody@mozilla.org",
            "f" + str(n + 2): "assigned_to",
            "o" + str(n + 2): "regexp",
            "v" + str(n + 2): r"^.*\.bugs$",
            "f" + str(n + 3): "assigned_to",
            "o" + str(n + 3): "isempty",
            "f" + str(n + 4): "CP",
        }
    )
    if negation:
        params["n" + str(n)] = 1

    return params


def is_no_assignee(mail):
    return mail == "nobody@mozilla.org" or mail.endswith(".bugs") or mail == ""


def get_login_info():
    with open(_CONFIG_PATH + "config.json", "r") as In:
        return json.load(In)


def get_private():
    with open(_CONFIG_PATH + "config.json", "r") as In:
        return json.load(In)["private"]


def get_gcp_service_account_info() -> dict:
    """Get the GCP service account info from the downloaded key file."""
    with open(
        _CONFIG_PATH + "gcp_service_account.json", "r", encoding="utf-8"
    ) as json_file:
        return json.load(json_file)


def plural(sword, data, pword=""):
    if isinstance(data, int):
        p = data != 1
    else:
        p = len(data) != 1
    if not p:
        return sword
    if pword:
        return pword
    return sword + "s"


def english_list(items):
    assert len(items) > 0
    if len(items) == 1:
        return items[0]

    return "{} and {}".format(", ".join(items[:-1]), items[-1])


def shorten_long_bz_url(url):
    if not url or len(url) <= MAX_URL_LENGTH:
        return url

    # the url can be very long and line length are limited in email protocol:
    # https://datatracker.ietf.org/doc/html/rfc5322#section-2.1.1
    # So we need to generate a short URL.

    def url_handler(u, data):
        data["url"] = u

    data = {}
    try:
        BugzillaShorten(url, url_data=data, url_handler=url_handler).wait()
    except HTTPError:  # workaround for https://github.com/mozilla/bugbot/issues/1402
        return "\n".join(
            [url[i : i + MAX_URL_LENGTH] for i in range(0, len(url), MAX_URL_LENGTH)]
        )

    return data["url"]


def get_cycle_span() -> str:
    """Return the cycle span in the format YYYYMMDD-YYYYMMDD"""
    global _CYCLE_SPAN
    if _CYCLE_SPAN is None:
        schedule = FirefoxTrains.get_instance().get_release_schedule("nightly")
        start = lmdutils.get_date_ymd(schedule["nightly_start"])
        end = lmdutils.get_date_ymd(schedule["merge_day"])

        now = lmdutils.get_date_ymd("today")
        assert start <= now <= end

        _CYCLE_SPAN = start.strftime("%Y%m%d") + "-" + end.strftime("%Y%m%d")

    return _CYCLE_SPAN


def get_next_release_date() -> datetime.datetime:
    """Return the next release date"""
    schedule = FirefoxTrains.get_instance().get_release_schedule("beta")
    release_date = lmdutils.get_date_ymd(schedule["release"])
    release_date = release_date.replace(hour=0, minute=0, second=0, microsecond=0)
    return release_date


def is_merge_day(date: datetime.datetime | None = None) -> bool:
    """Check if the date is the merge day

    Args:
        date: the date to check. If None, the current date is used.

    Returns:
        True if the date is the merge day
    """
    if date is None:
        date = lmdutils.get_date_ymd("today")

    schedule = FirefoxTrains.get_instance().get_release_schedule("nightly")
    last_merge = lmdutils.get_date_ymd(schedule["nightly_start"])
    next_merge = lmdutils.get_date_ymd(schedule["merge_day"])

    return date in (next_merge, last_merge)


def get_report_bugs(channel, op="+"):
    url = "https://bugzilla.mozilla.org/page.cgi?id=release_tracking_report.html"
    params = {
        "q": "approval-mozilla-{}:{}:{}:0:and:".format(channel, op, get_cycle_span())
    }

    # allow_redirects=False avoids to load the data
    # and we'll just get the redirected url to get all the bug ids we need
    r = requests.get(url, params=params, allow_redirects=False)

    # something like https://bugzilla.mozilla.org/buglist.cgi?bug_id=1493711,1502766,1499908
    url = r.headers["Location"]

    return url.split("=")[1].split(",")


def get_flag(version, name, channel):
    if name in ["status", "tracking"]:
        if channel == "esr":
            return "cf_{}_firefox_esr{}".format(name, version)
        return "cf_{}_firefox{}".format(name, version)
    elif name == "approval":
        if channel == "esr":
            return "approval-mozilla-esr{}".format(version)
        return "approval-mozilla-{}".format(channel)


def get_needinfo(bug, days=-1):
    now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    for flag in bug.get("flags", []):
        if flag.get("name", "") == "needinfo" and flag["status"] == "?":
            date = flag["modification_date"]
            date = dateutil.parser.parse(date)
            if (now - date).days >= days:
                yield flag


def get_last_field_num(params):
    s = set()
    for k in params.keys():
        m = BZ_FIELD_PAT.match(k)
        if m:
            s.add(int(m.group(1)))

    x = max(s) + 1 if s else 1
    return str(x)


def add_prod_comp_to_query(params, prod_comp):
    n = int(get_last_field_num(params))
    params[f"j{n}"] = "OR"
    params[f"f{n}"] = "OP"
    n += 1
    for pc in prod_comp:
        prod, comp = pc.split("::")
        params[f"j{n}"] = "AND"
        params[f"f{n}"] = "OP"
        n += 1
        params[f"f{n}"] = "product"
        params[f"o{n}"] = "equals"
        params[f"v{n}"] = prod
        n += 1
        params[f"f{n}"] = "component"
        params[f"o{n}"] = "equals"
        params[f"v{n}"] = comp
        n += 1
        params[f"f{n}"] = "CP"
        n += 1
    params[f"f{n}"] = "CP"


def get_bz_search_url(params):
    return "https://bugzilla.mozilla.org/buglist.cgi?" + urlencode(params, doseq=True)


def has_bot_set_ni(bug):
    bot = get_config("common", "bot_bz_mail")
    for flag in get_needinfo(bug):
        if flag["setter"] in bot:
            return True
    return False


def get_triage_owners():
    global _TRIAGE_OWNERS
    if _TRIAGE_OWNERS is not None:
        return _TRIAGE_OWNERS

    # accessible is the union of:
    #  selectable (all product we can see)
    #  enterable (all product a user can file bugs into).
    prods = get_config("common", "products")
    url = "https://bugzilla.mozilla.org/rest/product"
    params = {
        "type": "accessible",
        "include_fields": ["name", "components.name", "components.triage_owner"],
        "names": prods,
    }
    r = requests.get(url, params=params)
    products = r.json()["products"]
    _TRIAGE_OWNERS = {}
    for prod in products:
        prod_name = prod["name"]
        for comp in prod["components"]:
            owner = comp["triage_owner"]
            if owner and not is_no_assignee(owner):
                comp_name = comp["name"]
                pc = f"{prod_name}::{comp_name}"
                if owner not in _TRIAGE_OWNERS:
                    _TRIAGE_OWNERS[owner] = [pc]
                else:
                    _TRIAGE_OWNERS[owner].append(pc)
    return _TRIAGE_OWNERS


def get_default_assignees():
    global _DEFAULT_ASSIGNEES
    if _DEFAULT_ASSIGNEES is not None:
        return _DEFAULT_ASSIGNEES

    # accessible is the union of:
    #  selectable (all product we can see)
    #  enterable (all product a user can file bugs into).
    prods = get_config("common", "products")
    url = "https://bugzilla.mozilla.org/rest/product"
    params = {
        "type": "accessible",
        "include_fields": ["name", "components.name", "components.default_assigned_to"],
        "names": prods,
    }
    r = requests.get(url, params=params)
    products = r.json()["products"]
    _DEFAULT_ASSIGNEES = {}
    for prod in products:
        prod_name = prod["name"]
        _DEFAULT_ASSIGNEES[prod_name] = dap = {}
        for comp in prod["components"]:
            comp_name = comp["name"]
            assignee = comp["default_assigned_to"]
            dap[comp_name] = assignee
    return _DEFAULT_ASSIGNEES


def organize(bugs, columns, key=None):
    if isinstance(bugs, dict):
        # we suppose that the values are the bugdata dict
        bugs = bugs.values()

    def identity(x):
        return x

    def bugid_key(x):
        return -int(x)

    lambdas = {"id": bugid_key}

    def mykey(p):
        return tuple(lambdas.get(c, identity)(x) for x, c in zip(p, columns))

    if len(columns) >= 2:
        res = [tuple(info[c] for c in columns) for info in bugs]
    else:
        c = columns[0]
        res = [info[c] for info in bugs]

    return sorted(res, key=mykey if not key else key)


def merge_bz_changes(c1, c2):
    if not c1:
        return c2
    if not c2:
        return c1

    assert set(c1.keys()).isdisjoint(
        c2.keys()
    ), "Merge changes with common keys is not a good idea"
    c = copy.deepcopy(c1)
    c.update(c2)

    return c


def is_test_file(path):
    e = os.path.splitext(path)[1][1:].lower()
    return "test" in path and e not in {"ini", "list", "in", "py", "json", "manifest"}


def get_better_name(name):
    if not name:
        return ""

    def repl(m):
        if m.start(0) == 0:
            return m.group(0)
        return ""

    if name.startswith("Nobody;"):
        s = "Nobody"
    else:
        s = PAR_PAT.sub("", name)
        s = BRA_PAT.sub("", s)
        s = DIA_PAT.sub("", s)
        s = COL_PAT.sub(repl, s)
        s = UTC_PAT.sub("", s)
        s = s.strip()
        if s.startswith(":"):
            s = s[1:]
    return s.encode("utf-8").decode("utf-8")


def is_backout(json):
    return json.get("backedoutby", "") != "" or bool(BACKOUT_PAT.search(json["desc"]))


def get_pushlog(startdate, enddate, channel="nightly"):
    """Get the pushlog from hg.mozilla.org"""
    # Get the pushes where startdate <= pushdate <= enddate
    # pushlog uses strict inequality, it's why we add +/- 1 second
    fmt = "%Y-%m-%d %H:%M:%S"
    startdate -= relativedelta(seconds=1)
    startdate = startdate.strftime(fmt)
    enddate += relativedelta(seconds=1)
    enddate = enddate.strftime(fmt)
    url = "{}/json-pushes".format(Mercurial.get_repo_url(channel))
    r = requests.get(
        url,
        params={"startdate": startdate, "enddate": enddate, "version": 2, "full": 1},
    )
    return r.json()


def get_bugs_from_desc(desc):
    """Get a bug number from the patch description"""
    return BUG_PAT.findall(desc)


def get_bugs_from_pushlog(startdate, enddate, channel="nightly"):
    pushlog = get_pushlog(startdate, enddate, channel=channel)
    bugs = set()
    for push in pushlog["pushes"].values():
        for chgset in push["changesets"]:
            if chgset.get("backedoutby", "") != "":
                continue
            desc = chgset["desc"]
            for bug in get_bugs_from_desc(desc):
                bugs.add(bug)
    return bugs


def get_checked_versions():
    # There are different reasons to not return versions:
    # i) we're merge day: the versions are changing
    # ii) not consecutive versions numbers
    # iii) bugzilla updated nightly version but p-d is not updated
    if is_merge_day():
        return {}

    versions = lmdversions.get(base=True)
    versions["central"] = versions["nightly"]

    v = [versions[k] for k in ["release", "beta", "central"]]
    versions = {k: str(v) for k, v in versions.items()}

    if v[0] + 2 == v[1] + 1 == v[2]:
        nightly_bugzilla = get_nightly_version_from_bz()
        if v[2] != nightly_bugzilla:
            from . import logger

            logger.info("Versions mismatch between Bugzilla and product-details")
            return {}
        return versions

    from . import logger

    logger.info("Not consecutive versions in product/details")
    return {}


def get_info_from_hg(json):
    res = {}
    push = json["pushdate"][0]
    push = datetime.datetime.utcfromtimestamp(push)
    push = lmdutils.as_utc(push)
    res["date"] = lmdutils.get_date_str(push)
    res["backedout"] = json.get("backedoutby", "") != ""
    m = BUG_PAT.search(json["desc"])
    res["bugid"] = m.group(1) if m else ""

    return res


def bz_ignore_case(s):
    return "[" + "][".join(c + c.upper() for c in s) + "]"


def check_product_component(data, bug):
    prod = bug["product"]
    comp = bug["component"]
    pc = prod + "::" + comp
    return pc in data or comp in data


def get_components(data):
    res = []
    for comp in data:
        if "::" in comp:
            _, comp = comp.split("::", 1)
        res.append(comp)
    return res


def get_products_components(data):
    prods = set()
    comps = set()
    for pc in data:
        if "::" in pc:
            p, c = pc.split("::", 1)
            prods.add(p)
        else:
            c = pc
        comps.add(c)
    return prods, comps


def ireplace(old, repl, text):
    return re.sub("(?i)" + re.escape(old), lambda m: repl, text)


def get_human_lag(date):
    today = pytz.utc.localize(datetime.datetime.utcnow())
    dt = dateutil.parser.parse(date) if isinstance(date, str) else date

    return humanize.naturaldelta(today - dt)


def get_nightly_version_from_bz():
    def bug_handler(bug, data):
        status = "cf_status_firefox"
        N = len(status)
        for k in bug.keys():
            if k.startswith(status):
                k = k[N:]
                if k.isdigit():
                    data.append(int(k))

    data = []
    Bugzilla(bugids=["1234567"], bughandler=bug_handler, bugdata=data).get_data().wait()

    return max(data)


def nice_round(val):
    return int(round(100 * val))


def is_bot_email(email: str) -> bool:
    """Check if the email is belong to a bot or component-watching account.

    Args:
        email: the account login email.
    """
    if email.endswith("@disabled.tld"):
        return False

    return email.endswith(".bugs") or email.endswith(".tld")


def get_last_no_bot_comment_date(bug: dict) -> str:
    """Get the create date of the last comment by non bot account.

    Args:
        bug: the bug dictionary; it must has the comments list.

    Returns:
        If no comments or all comments are posted by bots, the creation date of
        the bug itself will be returned.
    """
    for comment in reversed(bug["comments"]):
        if not is_bot_email(comment["creator"]):
            return comment["creation_time"]

    return bug["comments"][0]["creation_time"]


def get_sort_by_bug_importance_key(bug):
    """
    We need bugs with high severity (S1 or S2) or high priority (P1 or P2) to be
    first (do not need to be high in both). Next, bugs with higher priority and
    severity are preferred. Finally, for bugs with the same severity and priority,
    we favour recently changed or created bugs.
    """

    is_important = bug["priority"] in HIGH_PRIORITY or bug["severity"] in HIGH_SEVERITY
    priority = bug["priority"] if bug["priority"].startswith("P") else "P10"
    severity = (
        bug["severity"]
        if bug["severity"].startswith("S")
        else OLD_SEVERITY_MAP.get(bug["severity"], "S10")
    )
    time_order = (
        lmdutils.get_timestamp(bug["last_change_time"])
        if "last_change_time" in bug
        else int(bug["id"])  # Bug ID reflects the creation order
    )

    return (
        not is_important,
        severity,
        priority,
        time_order * -1,
    )


def get_mail_to_ni(bug: dict) -> Union[dict, None]:
    """Get the person that should be needinfoed about the bug.

    If the bug is assigned, the assignee will be selected. Otherwise, will
    fallback to the triage owner.

    Args:
        bug: The bug that you need to send a needinfo request about.

    Returns:
        A dict with the nicname and the email of the person that should receive
        the needinfo request. If not available will return None.

    """

    for field in ["assigned_to", "triage_owner"]:
        person = bug.get(field, "")
        if not is_no_assignee(person):
            return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

    return None


def get_name_from_user_detail(detail: dict) -> str:
    """Get the name of the user from the detail object.

    Returns:
        The name of the user or the email as a fallback.
    """
    name = detail["real_name"]
    if is_no_assignee(detail["email"]):
        name = "nobody"
    if name.strip() == "":
        name = detail["name"]
        if name.strip() == "":
            name = detail["email"]

    return name


def is_weekend(date: Union[datetime.datetime, str]) -> bool:
    """Get if the provided date is a weekend day (Saturday or Sunday)"""
    parsed_date = lmdutils.get_date_ymd(date)
    return parsed_date.weekday() >= 5


def get_whiteboard_access_rating(whiteboard: str) -> str:
    """Get the access rating tag from the whiteboard.

    Args:
        whiteboard: a whiteboard string that contains an access rating tag.

    Returns:
        An access rating tag.
    """

    access_tags = WHITEBOARD_ACCESS_PAT.findall(whiteboard)
    assert len(access_tags) == 1, "Should have only one access tag"

    return access_tags[0]


def create_bug(bug_data: dict) -> dict:
    """Create a new bug.

    Args:
        bug_data: The bug data to create.

    Returns:
        A dictionary with the bug id of the newly created bug.
    """
    resp = requests.post(
        url=Bugzilla.API_URL,
        json=bug_data,
        headers=Bugzilla([]).get_header(),
        verify=True,
        timeout=Bugzilla.TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def is_keywords_removed_by_bugbot(bug: dict, keywords: Iterable) -> bool:
    """Check if the bug had any of the provided keywords removed by bugbot.

    Args:
        bug: The bug to check.
        keywords: The keywords to check.

    Returns:
        True if any of the keywords was removed by bugbot, False otherwise.
    """
    return any(
        keyword in change["removed"]
        for entry in bug["history"]
        if entry["who"] == BOT_MAIN_ACCOUNT
        for change in entry["changes"]
        if change["field_name"] == "keywords"
        for keyword in keywords
    )


def get_bug_bugdash_url(component, tab_name: str) -> str:
    """
    Generate bugdash URL for a component.

    Args:
        component: The name of the targeted component.
        tab_name: The name of the tab that should be active.

    Returns:
         A URL pointing to Bugdash based on the provided component and tab.
    """
    # Bugdash uses a single colon instead of a double colon to prefix the product name.
    encoded_component = quote_plus(f"{component.product}:{component.name}")

    return f"https://bugdash.moz.tools/?component={encoded_component}#tab.{tab_name}"
