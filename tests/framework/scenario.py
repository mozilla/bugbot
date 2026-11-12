# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Load, run and check rule scenarios."""

import copy
import datetime
import importlib
import inspect
import os
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest import mock

import responses
import time_machine
import yaml
from libmozdata import utils as lmdutils
from libmozdata.fx_trains import FirefoxTrains

from bugbot import db, utils
from bugbot.bzcleaner import BzCleaner, SilentBugzilla
from bugbot.nag_me import Nag
from bugbot.people import People
from tests.framework.bugs import link_bugs, make_user, normalize_bug
from tests.framework.fake_bugzilla import NOMAIL_TOKEN, FakeBugzilla

# Module-level caches of `bugbot.utils`, which must not leak between runs.
UTILS_CACHES = (
    "_CYCLE_SPAN",
    "_MERGE_DAY",
    "_TRIAGE_OWNERS",
    "_DEFAULT_ASSIGNEES",
    "_CURRENT_VERSIONS",
)

SCENARIOS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scenarios")


# YAML


class Contains:
    """`!contains text` in an expectation: a string containing `text`."""

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return f"!contains {self.text!r}"


class Anything:
    """`!any` in an expectation: the key must be present, with any value."""

    def __repr__(self):
        return "!any"


class _Loader(yaml.SafeLoader):
    pass


# Keep dates as strings, as Bugzilla returns them.
_Loader.yaml_implicit_resolvers = {
    key: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != "tag:yaml.org,2002:timestamp"
    ]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _construct_contains(loader: yaml.SafeLoader, node: yaml.Node) -> Contains:
    assert isinstance(node, yaml.ScalarNode)
    return Contains(loader.construct_scalar(node))


def _construct_any(loader: yaml.SafeLoader, node: yaml.Node) -> Anything:
    return Anything()


_Loader.add_constructor("!contains", _construct_contains)
_Loader.add_constructor("!any", _construct_any)


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.yaml_implicit_resolvers = _Loader.yaml_implicit_resolvers


def _str_representer(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str_representer)


def dump_yaml(data) -> str:
    return yaml.dump(
        data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=88
    )


def load_yaml(path: str):
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)


# Scenario


@dataclass
class Scenario:
    """A set of bugs, and what a rule is expected to do with them.

    Attributes:
        rule: the rule module, relative to `bugbot.rules` (e.g. `uplift_beta`
            or `workflow.p1`), optionally followed by `:ClassName` when the
            module defines several rules.
        bugs: the bugs, as returned by Bugzilla; only `id` is required (see
            `tests.framework.bugs` for the defaults). `comments`, `history`
            and `attachments` are served by their own endpoints.
        now: the frozen current time, which is also the date the rule runs.
        date: the `--date` the rule runs with, `today` by default.
        versions: the Firefox versions (`nightly`, `beta`, `release`, `esr`,
            ...), for the rules that need them.
        users: Bugzilla users, keyed by email. Users not defined are active.
        people: the Mozilla people directory (entries of `people.json`).
        components: the components, keyed by `Product::Component`, with their
            `default_assigned_to`, `triage_owner`, `team_name`... The
            components of the bugs exist anyway, with the bugs' triage owner.
        config: overrides of the rule's entries in `configs/rules.json`.
        rule_args: keyword arguments for the rule constructor.
        rule_attrs: attributes to set on the rule after its construction.
        release_schedule: the schedules returned by whattrainisitnow, keyed by
            channel (`beta`, `nightly`) or version, e.g.
            `{"beta": {"release": "2026-11-24"}}`.
        http: other HTTP responses: dicts with `url`, and `json` or `body`,
            and optionally `method` and `status`.
        render_email: whether to render the email, to check its template.
        recorded_from: how the scenario was recorded (informational).
        expect: the expected outcome, see `check`.
    """

    rule: str
    bugs: list[dict]
    name: str = ""
    description: str = ""
    now: str = "2026-01-01T12:00:00Z"
    date: str = "today"
    versions: dict | None = None
    users: list[dict] = field(default_factory=list)
    people: list[dict] = field(default_factory=list)
    components: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    rule_args: dict = field(default_factory=dict)
    rule_attrs: dict = field(default_factory=dict)
    release_schedule: dict = field(default_factory=dict)
    http: list[dict] = field(default_factory=list)
    render_email: bool = True
    recorded_from: dict | None = None
    expect: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict, **defaults) -> "Scenario":
        data = {**defaults, **data}
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        assert not unknown, f"Unknown scenario keys: {sorted(unknown)}"
        return cls(**data)


def load_scenario(path: str) -> Scenario:
    """Load a scenario file; the rule defaults to the name of its directory."""
    rule = os.path.basename(os.path.dirname(os.path.abspath(path)))
    name = os.path.splitext(os.path.basename(path))[0]
    return Scenario.from_dict(load_yaml(path), rule=rule, name=name)


def discover_scenarios(root: str = SCENARIOS_DIR) -> list[str]:
    paths = []
    for dirpath, _, filenames in os.walk(root):
        paths += [
            os.path.join(dirpath, f) for f in filenames if f.endswith((".yaml", ".yml"))
        ]
    return sorted(paths)


def get_rule_class(rule: str) -> type[BzCleaner]:
    module_name, _, class_name = rule.partition(":")
    module = importlib.import_module(f"bugbot.rules.{module_name}")
    if class_name:
        return getattr(module, class_name)

    classes = [
        obj
        for obj in vars(module).values()
        if inspect.isclass(obj)
        and issubclass(obj, BzCleaner)
        and obj.__module__ == module.__name__
    ]
    assert len(classes) == 1, (
        f"bugbot.rules.{module_name} defines {len(classes)} rules, "
        f"use `rule: {module_name}:ClassName` to pick one"
    )
    return classes[0]


# Running


@dataclass
class Result:
    """The outcome of a rule run.

    Attributes:
        ran: False if the rule decided not to run (`must_run` or
            `has_enough_data`), as it would in production.
        email: the rows of the email, keyed by bug id.
        changes: the changes sent to Bugzilla, keyed by bug id. A bug changed
            several times has a list of changes.
        silent: the ids of the bugs changed without sending bugmail.
        nags: for nag rules, the ids of the bugs each person is nagged about.
        searches: the searches made by the rule, with the ids of the bugs they
            matched.
        created: the bugs created on Bugzilla.
        email_body: the rendered email, if any.
        rule: the rule instance, for custom assertions.
    """

    ran: bool
    email: dict[str, dict]
    changes: dict[str, Any]
    silent: list[str]
    nags: dict[str, list[str]]
    searches: list[dict]
    created: list[dict]
    email_body: str | None
    rule: Any = None

    def as_expectation(self) -> dict:
        expect: dict[str, Any] = {
            "email": sorted(map(int, self.email)),
            "changes": {
                int(k): v
                for k, v in sorted(self.changes.items(), key=lambda x: int(x[0]))
            },
        }
        if self.nags:
            expect["nags"] = {
                person: sorted(map(int, bugids)) for person, bugids in self.nags.items()
            }
        if self.silent:
            expect["silent"] = sorted(map(int, self.silent))
        if self.created:
            expect["created"] = self.created
        return expect


def schedule_url(channel) -> str:
    return f"{FirefoxTrains.URL}release/schedule/?version={channel}"


def _to_utc_iso(value) -> str:
    if isinstance(value, (datetime.date, datetime.datetime)):
        value = value.isoformat()
    dt = lmdutils.get_date_ymd(value)
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def execute_rule(rule: BzCleaner, date: str, render_email: bool = True):
    """Run a rule as `BzCleaner.run` would, without sending emails.

    Changes are really sent to Bugzilla (which is expected to be mocked).

    Returns:
        (ran, email rows keyed by bug id, rendered email or None)
    """
    captured: dict[str, Any] = {}
    organize = rule.organize

    def capture_organize(bugs):
        captured["bugs"] = copy.deepcopy(dict(bugs))
        return organize(bugs)

    setattr(rule, "organize", capture_organize)
    rule.dryrun = False
    rule.is_limited = True
    rule.cache.set_dry_run(True)

    date = "" if rule.ignore_date() else date
    if date:
        date = lmdutils.get_date(date)
        d = lmdutils.get_date_ymd(date)
        if isinstance(rule, Nag):
            rule.nag_date = d
        if not rule.must_run(d):
            return False, {}, None
    if not rule.has_enough_data():
        return False, {}, None

    data = rule.get_email_data(date)
    if not data:
        rows = {}
    elif "bugs" in captured:
        rows = {str(k): v for k, v in captured["bugs"].items()}
    else:
        rows = {
            str(row["id"] if isinstance(row, dict) else row[0]): row for row in data
        }

    body = None
    if data and render_email:
        _, body = rule.get_email(date, data)

    return True, rows, body


def _versions(versions: dict | None):
    def get(*args, **kwargs):
        assert (
            versions is not None
        ), "The rule needs the Firefox versions: add `versions` to the scenario"
        res = {"esr_previous": versions.get("esr"), **versions}
        res.setdefault("central", res.get("nightly"))
        res.setdefault("nightly", res.get("central"))
        return res

    return get


@contextmanager
def mocked_environment(scenario: Scenario, rule_name: str):
    """Mock everything external to the rule: Bugzilla, time, versions, people..."""
    now = _to_utc_iso(scenario.now)
    users = {u["name"]: make_user(u["name"], u, now=now) for u in scenario.users}
    bugs = {}
    for bug in scenario.bugs:
        bug = normalize_bug(bug, users, now, scenario.versions)
        assert bug["id"] not in bugs, f"Bug {bug['id']} is defined twice"
        bugs[bug["id"]] = bug
    link_bugs(bugs)

    fake = FakeBugzilla(bugs, users, now, scenario.components)

    config = copy.deepcopy(utils._get_config())
    config.setdefault(rule_name, {}).update(scenario.config)

    get_versions = _versions(scenario.versions)
    with ExitStack() as stack:
        rsps = stack.enter_context(
            responses.RequestsMock(assert_all_requests_are_fired=False)
        )
        fake.register(rsps)
        for channel, schedule in scenario.release_schedule.items():
            rsps.add(
                "GET",
                schedule_url(channel),
                json={
                    k: v.isoformat() if isinstance(v, datetime.date) else v
                    for k, v in schedule.items()
                },
            )
        for entry in scenario.http:
            entry = dict(entry)
            rsps.add(
                entry.pop("method", "GET"),
                entry.pop("url"),
                **entry,
            )

        stack.enter_context(time_machine.travel(now, tick=False))
        for name in (
            "get_checked_versions",
            "get_versions_from_trains",
        ):
            stack.enter_context(mock.patch.object(utils, name, get_versions))
        stack.enter_context(
            mock.patch.object(
                utils,
                "get_nightly_version_from_bz",
                lambda: get_versions()["nightly"],
            )
        )
        stack.enter_context(mock.patch.object(utils, "_CONFIG", config))
        for cache in UTILS_CACHES:
            stack.enter_context(mock.patch.object(utils, cache, None))
        stack.enter_context(
            mock.patch.object(People, "_instance", People(scenario.people))  # type: ignore[arg-type]
        )
        stack.enter_context(mock.patch.object(FirefoxTrains, "_instance", None))
        stack.enter_context(mock.patch.object(SilentBugzilla, "TOKEN", NOMAIL_TOKEN))
        stack.enter_context(mock.patch.object(db.BugChange, "add"))
        stack.enter_context(mock.patch.object(db.Email, "add"))
        yield fake


def run_scenario(scenario: Scenario) -> Result:
    rule_cls = get_rule_class(scenario.rule)
    rule_name = scenario.rule.partition(":")[0].rsplit(".", 1)[-1]
    with mocked_environment(scenario, rule_name) as fake:
        rule = rule_cls(**scenario.rule_args)
        for attr, value in scenario.rule_attrs.items():
            setattr(rule, attr, value)
        try:
            ran, email, body = execute_rule(rule, scenario.date, scenario.render_email)
        except Exception as e:
            # The errors of the fake Bugzilla are the root cause, the rule
            # usually crashes on the error response.
            if fake.errors:
                raise AssertionError("\n".join(fake.errors)) from e
            raise

    assert not fake.errors, "\n".join(fake.errors)
    changes = {k: v[0] if len(v) == 1 else v for k, v in fake.changes.items()}
    silent = sorted(fake.silent, key=int)
    return Result(
        ran,
        email,
        changes,
        silent,
        get_nags(rule),
        fake.searches,
        fake.created,
        body,
        rule,
    )


def get_nags(rule) -> dict[str, list[str]]:
    """The bugs each person is nagged about: `Nag.data` is keyed by manager,
    then by person."""
    if not isinstance(rule, Nag) or not rule.data:
        return {}
    nags: dict[str, set[str]] = {}
    for persons in rule.data.values():
        for person, bugs in persons.items():
            nags.setdefault(person, set()).update(str(b["id"]) for b in bugs)
    return {p: sorted(ids, key=int) for p, ids in sorted(nags.items())}


# Checking


def _match(expected, actual, path: str, errors: list[str]) -> None:
    if isinstance(expected, Anything):
        return
    if isinstance(expected, Contains):
        if not isinstance(actual, str) or expected.text not in actual:
            errors.append(
                f"{path}: expected a string containing {expected.text!r}, got {actual!r}"
            )
        return
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            errors.append(f"{path}: expected a dict, got {actual!r}")
            return
        for key, value in expected.items():
            sub = f"{path}.{key}"
            if value is None:
                if actual.get(key) is not None:
                    errors.append(f"{sub}: expected no value, got {actual[key]!r}")
            elif key not in actual:
                errors.append(f"{sub}: missing")
            else:
                _match(value, actual[key], sub, errors)
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            errors.append(f"{path}: expected {expected!r}, got {actual!r}")
            return
        for i, (e, a) in enumerate(zip(expected, actual)):
            _match(e, a, f"{path}[{i}]", errors)
        return
    if expected != actual:
        errors.append(f"{path}: expected {expected!r}, got {actual!r}")


def _match_by_bug(expected, actual: dict, path: str, errors: list[str]) -> None:
    if isinstance(expected, list):
        expected = {bugid: Anything() for bugid in expected}
    expected = {str(k): v for k, v in (expected or {}).items()}
    if set(expected) != set(actual):
        errors.append(
            f"{path}: expected bugs {sorted(expected, key=int)}, "
            f"got {sorted(actual, key=int)}"
        )
    for bugid in sorted(set(expected) & set(actual), key=int):
        _match(expected[bugid], actual[bugid], f"{path}[{bugid}]", errors)


def check(result: Result, expect: dict) -> list[str]:
    """Compare a result with the expectations of a scenario.

    - `email`: the bugs in the email, as a list of ids, or as a dict mapping
      the ids to (a subset of) their row in the email.
    - `changes`: (a subset of) the changes, keyed by bug id. Bugs not listed
      must not be changed.
    - `nags`: for nag rules, the bug ids each person is nagged about.
    - `silent`: the ids of the bugs changed without sending bugmail.
    - `created`: (a subset of) the bugs created.
    - `email_contains`: strings the rendered email must contain.
    - `ran`: whether the rule should run at all (true by default).

    Dicts are compared on the expected keys only: a `null` value means that the
    key must be absent, `!any` that it must be present, and `!contains text`
    matches any string containing `text`. Lists and other values must be equal.
    Unspecified entries are not checked.
    """
    errors: list[str] = []
    if result.ran != expect.get("ran", True):
        errors.append(f"ran: expected {expect.get('ran', True)}, got {result.ran}")
    if "email" in expect:
        _match_by_bug(expect["email"], result.email, "email", errors)
    if "changes" in expect:
        _match_by_bug(expect["changes"], result.changes, "changes", errors)
    if "silent" in expect:
        silent = sorted(map(str, expect["silent"]), key=int)
        if silent != result.silent:
            errors.append(f"silent: expected {silent}, got {result.silent}")
    if "nags" in expect:
        expected = {
            p: sorted(map(str, ids), key=int)
            for p, ids in (expect["nags"] or {}).items()
        }
        if expected != result.nags:
            errors.append(f"nags: expected {expected}, got {result.nags}")
    if "created" in expect:
        _match(expect["created"], result.created, "created", errors)
    for text in expect.get("email_contains", []):
        if text not in (result.email_body or ""):
            errors.append(f"email_contains: {text!r} not in the email")
    return errors


def assert_scenario(scenario: Scenario | dict, **kwargs) -> Result:
    """Run a scenario and check its expectations; return the result.

    Can be used from regular tests, e.g.:

        assert_scenario(
            {"rule": "closed_bug_ni_cleanup", "bugs": [...], "expect": {...}},
            now="2026-10-16",
        )
    """
    if isinstance(scenario, dict):
        scenario = Scenario.from_dict({**kwargs, **scenario})
    result = run_scenario(scenario)
    errors = check(result, scenario.expect)
    assert not errors, "Unexpected outcome:\n  " + "\n  ".join(errors)
    return result
