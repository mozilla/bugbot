# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Record a scenario from real Bugzilla bugs.

    python -m tests.framework.record RULE BUG [BUG ...] [--name NAME]

The rule runs for real, except that:
- its Bugzilla searches are restricted to the given bugs;
- nothing is written: changes to Bugzilla are intercepted, and any other
  non-GET request is blocked;
- no email is sent.

The bugs the rule fetched are saved with all their data (as the queries may
depend on any field), with everything else it fetched (users, other HTTP
resources), the time and the Firefox versions. Then:
- each search of the rule is run again on Bugzilla, restricted to the recorded
  bugs, and compared with what the fake Bugzilla's evaluation of the search
  gives (see `tests.framework.search`): any difference is a bug there;
- the scenario is replayed against the fake Bugzilla, its outcome is saved as
  its expectations, and compared with the live run;
- the data the outcome doesn't depend on is removed (see `minimize_scenario`).

If a bug fetched by the rule (e.g. a regressor) also matches its searches, it
is added to the bugs to record, as the replay will consider it too.

Private bugs are never recorded, and private comments and attachments are
dropped.
"""

import argparse
import copy
import datetime
import json
import logging
import os
import sys
import threading
from collections import defaultdict
from contextlib import ExitStack
from unittest import mock
from urllib.parse import parse_qs, urlparse, urlunparse

import requests
import yaml
from libmozdata.bugzilla import Bugzilla

import bugbot
from bugbot import db, utils
from bugbot.people import People
from tests.framework.bugs import link_bugs, make_user, normalize_bug, strip_defaults
from tests.framework.scenario import (
    SCENARIOS_DIR,
    UTILS_CACHES,
    Scenario,
    _Loader,
    check,
    dump_yaml,
    execute_rule,
    get_nags,
    get_rule_class,
    load_yaml,
    run_scenario,
    schedule_url,
)
from tests.framework.search import (
    InvalidSearch,
    Search,
    parse_datetime,
    search_criteria,
)

BZ_HOST = urlparse(Bugzilla.URL).netloc
BUG_PATH = urlparse(Bugzilla.API_URL).path
USER_PATH = "/rest/user"
PRODUCT_PATH = "/rest/product"

PEOPLE_FIELDS = (
    "mail",
    "bugzillaEmail",
    "cn",
    "dn",
    "manager",
    "ismanager",
    "isdirector",
    "title",
)


class PrivateDataError(Exception):
    pass


class BlockedRequestError(Exception):
    pass


def _fake_response(request, body: dict) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(body).encode()
    response.headers["Content-Type"] = "application/json"
    response.url = request.url
    response.request = request
    return response


class Recorder:
    def __init__(self, bug_ids: list[int]):
        self.bug_ids = [str(i) for i in bug_ids]
        self.bugs: dict[int, dict] = {}
        # The searches made by the rule, before restricting them.
        self.searches: list[dict] = []
        self.users: dict[str, dict] = {}
        self.components: dict[str, dict] = {}
        # The fields the rule explicitly asked for, by bug.
        self.explicit_fields: dict[int, set[str]] = defaultdict(set)
        self.http: list[dict] = []
        self.changes: dict[str, list] = defaultdict(list)
        self.created: list[dict] = []
        self.versions = None
        self.suppressed = 0
        self._lock = threading.Lock()

    # HTTP interception

    def install(self, stack: ExitStack) -> None:
        send = requests.adapters.HTTPAdapter.send
        recorder = self

        def patched_send(adapter, request, *args, **kwargs):
            return recorder.send(lambda r: send(adapter, r, *args, **kwargs), request)

        stack.enter_context(
            mock.patch.object(requests.adapters.HTTPAdapter, "send", patched_send)
        )

    def send(self, send, request):
        url = urlparse(request.url)
        params = parse_qs(url.query, keep_blank_values=True)
        is_bz = url.netloc == BZ_HOST

        if request.method != "GET":
            if not is_bz:
                raise BlockedRequestError(
                    f"Blocked {request.method} {request.url}: only Bugzilla writes "
                    "are intercepted, mock this request by hand in the scenario."
                )
            body = json.loads(request.body or b"{}")
            with self._lock:
                if request.method == "PUT":
                    bugid = url.path.rstrip("/").rsplit("/", 1)[-1]
                    for i in body.pop("ids", [bugid]):
                        self.changes[str(i)].append(copy.deepcopy(body))
                    return _fake_response(request, {"bugs": []})
                self.created.append(body)
                return _fake_response(request, {"id": 9_000_000 + len(self.created)})

        if self.suppressed:
            return send(request)

        if is_bz and url.path.rstrip("/") == BUG_PATH and "id" not in params:
            criteria = search_criteria(params)
            with self._lock:
                if criteria not in self.searches:
                    self.searches.append(criteria)
            request = self._restrict_search(request, url, params)
            params = parse_qs(urlparse(request.url).query, keep_blank_values=True)

        response = send(request)
        if response.status_code != 200:
            return response

        try:
            data = response.json()
        except ValueError:
            data = None

        with self._lock:
            bz_paths = (BUG_PATH, USER_PATH, PRODUCT_PATH)
            if is_bz and url.path.startswith(bz_paths) and data is not None:
                self._record_bugzilla(url.path.rstrip("/"), params, data)
            else:
                entry = {"url": request.url}
                if data is not None:
                    entry["json"] = data
                else:
                    entry["body"] = response.text
                self.http.append(entry)
        return response

    def _restrict_search(self, request, url, params):
        """Restrict a search to the bugs to record."""
        if "bug_id" in params:
            return request
        params["bug_id"] = [",".join(self.bug_ids)]
        request = request.copy()
        request.prepare_url(urlunparse(url._replace(query="")), params)
        return request

    def _record_bugzilla(self, path, params, data):
        if path == USER_PATH:
            for user in data.get("users", []):
                self.users.setdefault(user["name"], {}).update(user)
            return
        if path == PRODUCT_PATH:
            for product in data.get("products", []):
                for component in product.get("components", []):
                    key = f"{product['name']}::{component['name']}"
                    component = {k: v for k, v in component.items() if k != "name"}
                    self.components.setdefault(key, {}).update(component)
            return

        rest = path[len(BUG_PATH) :].strip("/").split("/")
        explicit = {
            f.partition(".")[0]
            for value in params.get("include_fields", [])
            for f in value.split(",")
            if f and not f.startswith("_")
        }
        if rest == [""] or (len(rest) == 1 and rest[0].isdigit()):
            for bug in data.get("bugs", []):
                self._bug(bug["id"]).update(bug)
                self.explicit_fields[int(bug["id"])] |= explicit
        elif len(rest) == 2 and rest[1] == "history":
            for bug in data.get("bugs", []):
                self._bug(bug["id"])["history"] = bug["history"]
        elif len(rest) == 2 and rest[1] == "comment":
            for bugid, value in (data.get("bugs") or {}).items():
                self._merge_list(self._bug(bugid), "comments", value["comments"])
        elif len(rest) == 2 and rest[1] == "attachment":
            for bugid, value in (data.get("bugs") or {}).items():
                self._merge_list(self._bug(bugid), "attachments", value)
        elif rest[0] == "attachment":
            for attachment in (data.get("attachments") or {}).values():
                self._merge_list(
                    self._bug(attachment["bug_id"]), "attachments", [attachment]
                )
        else:
            raise NotImplementedError(f"Unsupported Bugzilla endpoint: {path}")

    def _bug(self, bugid) -> dict:
        return self.bugs.setdefault(int(bugid), {"id": int(bugid)})

    @staticmethod
    def _merge_list(bug, key, items):
        if not all("id" in item for item in items):
            # Fetched without their ids (`include_fields`): they're replaced
            # by the full data at the end anyway.
            bug[key] = items
            return
        existing = {item["id"]: item for item in bug.get(key, []) if "id" in item}
        for item in items:
            existing.setdefault(item["id"], {}).update(item)
        bug[key] = sorted(existing.values(), key=lambda item: item["id"])

    # Versions

    def wrap_versions(self, stack: ExitStack) -> None:
        """Record the versions, without recording the requests to get them."""
        for name in ("get_checked_versions", "get_versions_from_trains"):
            original = getattr(utils, name)

            def wrapper(*args, _original=original, **kwargs):
                self.suppressed += 1
                try:
                    res = _original(*args, **kwargs)
                finally:
                    self.suppressed -= 1
                if res and self.versions is None:
                    self.versions = {k: v for k, v in res.items() if k != "central"}
                return res

            stack.enter_context(mock.patch.object(utils, name, wrapper))

    # Output

    def check_private(self) -> list[str]:
        """Fail on private bugs, drop private comments and attachments."""
        warnings = []
        for bug in self.bugs.values():
            if bug.get("groups"):
                raise PrivateDataError(f"Bug {bug['id']} is private: {bug['groups']}")
            for key in ("comments", "attachments"):
                items = bug.get(key, [])
                public = [item for item in items if not item.get("is_private")]
                if len(public) != len(items):
                    bug[key] = public
                    warnings.append(f"Dropped the private {key} of bug {bug['id']}")
        return warnings

    def add_full_data(self, bug_ids) -> None:
        """Replace the bugs with all their data, as returned by Bugzilla."""
        for bug in fetch_bugs(bug_ids):
            self.bugs[int(bug["id"])] = bug


def _bz_headers() -> dict:
    return {"X-Bugzilla-API-Key": Bugzilla.TOKEN} if Bugzilla.TOKEN else {}


def fetch_bugs(bug_ids) -> list[dict]:
    """All the data of some bugs (comments, history, attachments...)."""
    bug_ids = sorted(map(int, bug_ids))
    bugs = []
    for i in range(0, len(bug_ids), 20):
        response = requests.get(
            Bugzilla.API_URL,
            params={
                "id": ",".join(map(str, bug_ids[i : i + 20])),
                "include_fields": "_all",
                "exclude_fields": "attachments.data",
            },
            headers=_bz_headers(),
            timeout=120,
        )
        response.raise_for_status()
        bugs += response.json()["bugs"]
    return bugs


def restrict(criteria: dict, bug_ids) -> dict:
    """Restrict a search to some bugs, as the recorder does."""
    ids = {str(i) for i in bug_ids}
    if "bug_id" in criteria:
        given = {i for v in criteria["bug_id"] for i in v.split(",") if i}
        ids &= given
    return {**criteria, "bug_id": [",".join(sorted(ids, key=int)) or "0"]}


def live_search(criteria: dict, bug_ids) -> set[int]:
    """The bugs among `bug_ids` matching a search, according to Bugzilla."""
    params = {**restrict(criteria, bug_ids), "include_fields": ["id"]}
    response = requests.get(
        Bugzilla.API_URL, params=params, headers=_bz_headers(), timeout=300
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise InvalidSearch(data.get("message", "error"))
    return {int(bug["id"]) for bug in data["bugs"]}


def cross_check_searches(truths, scenario: dict) -> list[str]:
    """Compare Bugzilla's results for the searches with the fake's evaluation."""
    now = parse_datetime(scenario["now"])
    assert now is not None
    users = {
        u["name"]: make_user(u["name"], u, now=scenario["now"])
        for u in scenario.get("users", [])
    }
    bugs = {}
    for bug in scenario["bugs"]:
        bug = normalize_bug(bug, users, scenario["now"], scenario.get("versions"))
        bugs[bug["id"]] = bug
    link_bugs(bugs)

    differences = []
    for criteria, expected in truths:
        params = restrict(criteria, bugs)
        try:
            search = Search(params, now, users)
            found = {i for i, bug in bugs.items() if search.matches(bug)}
        except AssertionError as e:
            differences.append(f"search {criteria}: {e}")
            continue
        if found != expected:
            differences.append(
                f"search {criteria}: Bugzilla matched {sorted(expected)}, "
                f"the fake Bugzilla matched {sorted(found)}"
            )
    return differences


def _strip_comment(bug, i, comment):
    defaults = {
        "count": i,
        "bug_id": bug["id"],
        "creator": comment.get("author"),
        "creation_time": comment.get("time"),
        "raw_text": comment.get("text"),
        "is_private": False,
        "attachment_id": None,
        "tags": [],
    }
    return {k: v for k, v in comment.items() if k not in defaults or defaults[k] != v}


def _strip_component(component, bugs):
    defaults = {
        "id": None,
        "default_assigned_to": "nobody@mozilla.org",
        "is_active": True,
        "team_name": "Mozilla",
    }
    return {
        k: v
        for k, v in component.items()
        if k != "id" and defaults.get(k, object()) != v
    }


def _strip_user(user, now):
    default = make_user(user["name"], now=now)
    return {
        k: v for k, v in user.items() if k == "name" or default.get(k, object()) != v
    }


def _people_subset(people: People, text: str) -> list[dict]:
    """The people.json entries of the people mentioned, and their managers."""
    by_dn = {p["dn"]: p for p in people.data if "dn" in p}
    selected = {}
    for person in people.data:
        emails = {person.get("mail"), person.get("bugzillaEmail")} - {None, ""}
        if any(email in text for email in emails):
            while person and person["dn"] not in selected:
                selected[person["dn"]] = {
                    k: person[k] for k in PEOPLE_FIELDS if k in person
                }
                person = by_dn.get((person.get("manager") or {}).get("dn"))
    return list(selected.values())


def _live_run(rule_cls, targets, date, with_people, rule_attrs):
    """Run the rule on Bugzilla, restricted to the target bugs."""
    recorder = Recorder(targets)
    with ExitStack() as stack:
        recorder.install(stack)
        recorder.wrap_versions(stack)
        stack.enter_context(mock.patch.object(db.BugChange, "add"))
        stack.enter_context(mock.patch.object(db.Email, "add"))
        for cache in UTILS_CACHES:
            stack.enter_context(mock.patch.object(utils, cache, None))
        if not with_people:
            stack.enter_context(mock.patch.object(People, "_instance", People([])))
        instance = rule_cls()
        for attr, value in (rule_attrs or {}).items():
            setattr(instance, attr, value)
        ran, email, _ = execute_rule(instance, date, render_email=False)
        nags = get_nags(instance)
    return recorder, ran, email, nags


def record(
    rule: str,
    bug_ids: list[int],
    date: str = "today",
    with_people: bool = False,
    rule_attrs: dict | None = None,
    description: str = "",
    minimize: bool = True,
    log=lambda message: print(message, file=sys.stderr),
) -> tuple[dict, list[str]]:
    """Record a scenario.

    Returns:
        The scenario, and the problems found: differences between Bugzilla's
        results and the fake's, for the searches and for the whole run.
    """
    rule_cls = get_rule_class(rule)
    targets = sorted({int(i) for i in bug_ids})
    for _ in range(5):
        now = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        recorder, ran, email, nags = _live_run(
            rule_cls, targets, date, with_people, rule_attrs
        )
        all_ids = sorted(set(recorder.bugs) | set(targets))
        truths = [(c, live_search(c, all_ids)) for c in recorder.searches]
        extra = set().union(*(found for _, found in truths)) - set(targets)
        if not extra:
            break
        log(
            f"Bugs {sorted(extra)} also match the rule's searches: "
            "recording them too"
        )
        targets = sorted(set(targets) | extra)
    else:
        raise RuntimeError("The bugs to record keep changing, giving up")

    recorder.add_full_data(all_ids)
    for warning in recorder.check_private():
        log(f"warning: {warning}")

    users = {name: _strip_user(user, now) for name, user in recorder.users.items()}
    bugs = []
    for bugid in sorted(recorder.bugs):
        bug = recorder.bugs[bugid]
        if "comments" in bug:
            bug["comments"] = [
                _strip_comment(bug, i, c) for i, c in enumerate(bug["comments"])
            ]
        bug = strip_defaults(bug, recorder.users, now)
        bugs.append({"id": bug.pop("id"), **bug})

    scenario: dict = {}
    if description:
        scenario["description"] = description
    scenario["recorded_from"] = {"bugs": targets}
    scenario["now"] = now
    if date != "today":
        scenario["date"] = date
    if recorder.versions:
        scenario["versions"] = recorder.versions
    if rule_attrs:
        scenario["rule_attrs"] = rule_attrs
    scenario["bugs"] = bugs
    if users:
        scenario["users"] = list(users.values())
    # Only the components of the recorded bugs, the products can be huge.
    bug_components = {
        f"{b['product']}::{b['component']}"
        for b in recorder.bugs.values()
        if "product" in b and "component" in b
    }
    components = {
        key: _strip_component(value, recorder.bugs)
        for key, value in sorted(recorder.components.items())
        if key in bug_components
    }
    components = {k: v for k, v in components.items() if v}
    if components:
        scenario["components"] = components
    if with_people:
        scenario["people"] = _people_subset(
            People.get_instance(), json.dumps([bugs, users])
        )
    schedules = {
        entry["url"].rpartition("=")[2]: entry["json"]
        for entry in recorder.http
        if entry["url"].startswith(schedule_url("")) and "json" in entry
    }
    http = [e for e in recorder.http if not e["url"].startswith(schedule_url(""))]
    if schedules:
        scenario["release_schedule"] = schedules
    if http:
        scenario["http"] = http

    problems = cross_check_searches(truths, scenario)

    if minimize:
        log("Removing the data the outcome doesn't depend on...")
        scenario = minimize_scenario(
            scenario, rule, keep_bugs=targets, keep_fields=recorder.explicit_fields
        )

    # Replay what will be written, to get the expectations.
    replayed = yaml.load(dump_yaml(scenario), Loader=_Loader)
    result = run_scenario(Scenario.from_dict(replayed, rule=rule))
    scenario["expect"] = result.as_expectation()
    if not ran:
        scenario["expect"]["ran"] = False

    live = {k: v[0] if len(v) == 1 else v for k, v in recorder.changes.items()}
    expect_live = {"email": sorted(email, key=int), "changes": live, "ran": ran}
    if nags:
        expect_live["nags"] = nags
    if recorder.created:
        expect_live["created"] = recorder.created
    problems += check(result, expect_live)
    # Partial matching: also check that the replay doesn't have extra changes.
    problems += [
        f"changes[{k}]: unexpected {key!r} in the replay"
        for k, change in result.changes.items()
        if k in live and isinstance(change, dict) and isinstance(live[k], dict)
        for key in set(change) - set(live[k])
    ]
    return scenario, problems


BUGBOT_DIR = os.path.dirname(os.path.abspath(bugbot.__file__))


def _traced(fn):
    """Call `fn`, and return its result and the lines of BugBot it executed
    (in all threads)."""
    lines = set()

    def local(frame, event, arg):
        if event == "line":
            lines.add((frame.f_code.co_filename, frame.f_lineno))
        return local

    def tracer(frame, event, arg):
        if frame.f_code.co_filename.startswith(BUGBOT_DIR):
            return local
        return None

    sys.settrace(tracer)
    threading.settrace(tracer)
    try:
        return fn(), lines
    finally:
        sys.settrace(None)
        threading.settrace(None)


def find_bugs(rule: str, limit: int, date: str = "today") -> list[dict]:
    """Recently changed public bugs matching the main query of a rule."""
    instance = get_rule_class(rule)()
    params = instance.get_bz_params(date)
    instance.amend_bzparams(params, [])
    params.update(
        limit=limit,
        include_fields=["id", "summary", "groups"],
        order="changeddate DESC",
    )
    response = requests.get(Bugzilla.API_URL, params=params, timeout=120)
    response.raise_for_status()
    return [bug for bug in response.json()["bugs"] if not bug["groups"]]


def _outcome(scenario: dict, rule: str) -> str | None:
    """A fingerprint of a run of the scenario: everything observable about
    its outcome, and the code of BugBot it went through."""
    try:
        result, lines = _traced(
            lambda: run_scenario(Scenario.from_dict(copy.deepcopy(scenario), rule=rule))
        )
    except Exception:
        return None
    observed = {
        "lines": sorted(lines),
        "ran": result.ran,
        "email": result.email,
        "body": result.email_body,
        "changes": result.changes,
        "silent": result.silent,
        "nags": result.nags,
        "created": result.created,
        "searches": [search["ids"] for search in result.searches],
    }
    return json.dumps(observed, sort_keys=True, default=str)


def _reduce(candidates: list, still_same) -> list:
    """The largest subset (found greedily) of `candidates` which can be
    removed while `still_same(removed)` holds, by halving the candidates."""
    removed: list = []

    def attempt(chunk):
        if not chunk:
            return
        if still_same(removed + chunk):
            removed.extend(chunk)
            return
        if len(chunk) > 1:
            middle = len(chunk) // 2
            attempt(chunk[:middle])
            attempt(chunk[middle:])

    attempt(list(candidates))
    return removed


def minimize_scenario(
    scenario: dict, rule: str, keep_bugs=(), keep_fields: dict | None = None
) -> dict:
    """Remove the data which doesn't matter to the rule.

    Tries to drop the entries of the optional sections, the fields of the bugs
    and users, and the items of the lists of dicts in the bugs (comments,
    history, flags...). A removal is kept when the replay is the same: same
    outcome (changes, email, nags...), same bugs matched by each search, and
    same lines of BugBot executed, so that a bug doesn't end up skipped for
    another reason.

    The bugs in `keep_bugs`, and the fields in `keep_fields` (by bug id), which
    the rule explicitly asked for, are always kept.
    """
    keep_fields = keep_fields or {}
    scenario = copy.deepcopy(scenario)
    baseline = _outcome(scenario, rule)
    if baseline is None:
        return scenario
    keep_bugs = {int(i) for i in keep_bugs}

    def same() -> bool:
        return _outcome(scenario, rule) == baseline

    def reduce_dict(obj: dict, protected=()) -> None:
        def still_same(keys):
            saved = {key: obj.pop(key) for key in keys}
            try:
                return same()
            finally:
                obj.update(saved)

        order = list(obj)
        removed = _reduce([k for k in order if k not in protected], still_same)
        kept = {key: obj[key] for key in order if key not in removed}
        obj.clear()
        obj.update(kept)

    def reduce_list(items: list, protected=lambda item: False) -> None:
        def still_same(indices):
            saved = list(items)
            items[:] = [item for i, item in enumerate(saved) if i not in indices]
            try:
                return same()
            finally:
                items[:] = saved

        candidates = [i for i, item in enumerate(items) if not protected(item)]
        removed = set(_reduce(candidates, still_same))
        items[:] = [item for i, item in enumerate(items) if i not in removed]

    logging.disable(logging.CRITICAL)
    try:
        for section in ("http", "users", "people"):
            if section in scenario:
                reduce_list(scenario[section])
                if not scenario[section]:
                    del scenario[section]
        for section in ("components", "release_schedule"):
            if section in scenario:
                reduce_dict(scenario[section])
                for value in scenario[section].values():
                    reduce_dict(value)
                if not scenario[section]:
                    del scenario[section]

        reduce_list(scenario["bugs"], protected=lambda bug: bug["id"] in keep_bugs)
        for bug in scenario["bugs"]:
            reduce_dict(bug, protected={"id"} | set(keep_fields.get(bug["id"], ())))
            for value in bug.values():
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    reduce_list(value)
                    for item in value:
                        reduce_dict(item, protected=("id", "name", "count"))
        for user in scenario.get("users", []):
            reduce_dict(user, protected=("name",))
    finally:
        logging.disable(logging.NOTSET)

    return scenario


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record a test scenario for a rule from real Bugzilla bugs."
    )
    parser.add_argument("rule", help="the rule, e.g. uplift_beta or workflow.p1")
    parser.add_argument("bugs", nargs="*", type=int, help="the bugs to run the rule on")
    parser.add_argument(
        "--find",
        type=int,
        metavar="N",
        help="don't record anything, list N recent bugs matching the rule's query",
    )
    parser.add_argument("--name", help="the scenario name (default: bug_<ids>)")
    parser.add_argument("--description", default="", help="what the scenario tests")
    parser.add_argument(
        "-D", "--date", default="today", help="the date to run the rule with"
    )
    parser.add_argument(
        "--people",
        action="store_true",
        help="include the entries of configs/people.json for the people involved "
        "(needed by nag rules). Review them before committing: this is not public data",
    )
    parser.add_argument(
        "--attr",
        action="append",
        default=[],
        metavar="NAME=JSON",
        help="set an attribute on the rule, e.g. --attr days_to_release=20",
    )
    parser.add_argument(
        "--no-minimize",
        dest="minimize",
        action="store_false",
        help="keep all the recorded data, instead of only what the outcome depends on",
    )
    parser.add_argument("-o", "--output", help="output path (- for stdout)")
    parser.add_argument("-f", "--force", action="store_true", help="overwrite")
    args = parser.parse_args(argv)

    if args.find:
        for bug in find_bugs(args.rule, args.find, args.date):
            print(bug["id"], bug["summary"])
        return
    if not args.bugs:
        parser.error("the bugs to record are required")

    rule_attrs = {}
    for attr in args.attr:
        name, _, value = attr.partition("=")
        rule_attrs[name] = json.loads(value)

    try:
        scenario, differences = record(
            args.rule,
            args.bugs,
            date=args.date,
            with_people=args.people,
            rule_attrs=rule_attrs,
            description=args.description,
            minimize=args.minimize,
        )
    except (PrivateDataError, BlockedRequestError, InvalidSearch) as e:
        sys.exit(f"error: {e}")

    text = dump_yaml(scenario)
    rule_dir = args.rule.partition(":")[0]
    output = args.output or os.path.join(
        SCENARIOS_DIR,
        rule_dir,
        (args.name or "bug_" + "_".join(map(str, args.bugs))) + ".yaml",
    )
    if output == "-":
        print(text)
    else:
        if os.path.exists(output) and not args.force:
            sys.exit(f"error: {output} already exists, use --force to overwrite")
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(text)
        # Make sure the file loads back the same.
        load_yaml(output)
        print(f"Wrote {output}", file=sys.stderr)

    expect = scenario["expect"]
    print(
        f"Outcome: ran={expect.get('ran', True)}, email={expect['email']}, "
        f"changed={sorted(expect['changes'])}",
        file=sys.stderr,
    )
    if differences:
        print(
            "warning: the fake Bugzilla differs from the real one, the scenario "
            "or the fake (e.g. its evaluation of searches) is missing "
            "something:\n  " + "\n  ".join(differences),
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
