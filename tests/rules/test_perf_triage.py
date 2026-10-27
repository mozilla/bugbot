# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from jinja2 import Environment, FileSystemLoader

from bugbot import utils
from bugbot.rules.perf_triage import HACKBOT_EMAIL, TRIAGED_COMPONENT, PerfTriage

REPORTER_MAIL = "reporter@example.org"
DATE = "2026-10-27"


def _rule(**over):
    rule = PerfTriage()
    for key, value in over.items():
        setattr(rule, key, value)
    return rule


def _bug(creator, bug_id=1):
    return {
        "id": bug_id,
        "summary": "YouTube tab grows to 10GB",
        "creator": creator,
        "product": "Core",
        "component": "Performance: General",
        "groups": [],
    }


# --- who gets triaged --------------------------------------------------- #


def test_keeps_a_human_filed_bug():
    assert _rule().handle_bug(_bug(REPORTER_MAIL), {}) is not None


def test_drops_a_bot_filed_bug():
    # update-bot@bmo.tld filed two of the 23 Performance: General bugs the query
    # matched between 2026-08-01 and 2026-10-27.
    assert _rule().handle_bug(_bug("update-bot@bmo.tld"), {}) is None


def test_reporter_reaches_the_report():
    rule = _rule(dryrun=True)
    rule.cache.set_dry_run(True)
    data: dict = {}
    rule.bughandler(_bug(REPORTER_MAIL), data)
    assert data["1"]["creator"] == REPORTER_MAIL
    assert set(rule.columns()) <= set(data["1"]) | {"run_id"}


# --- which bugs are queried --------------------------------------------- #


def _chart(params):
    """The boolean chart as nested lists of `(field, operator, value)` clauses.

    Walks the numbered fields rather than naming `f3`/`v3`, so the tests still
    mean something if the numbering shifts.
    """
    indexes = sorted(int(k[1:]) for k in params if k[0] == "f" and k[1:].isdigit())
    stack: list = [[]]
    for i in indexes:
        field = params[f"f{i}"]
        if field == "OP":
            group = {"join": params.get(f"j{i}", "AND"), "items": []}
            stack[-1].append(group)
            stack.append(group["items"])
        elif field == "CP":
            stack.pop()
        else:
            negated = bool(params.get(f"n{i}"))
            stack[-1].append((negated, field, params[f"o{i}"], params[f"v{i}"]))
    assert len(stack) == 1, "unbalanced OP/CP"
    return stack[0]


def _branches(params):
    """The top-level OR's two branches."""
    (top,) = [item for item in _chart(params) if isinstance(item, dict)]
    assert top["join"] == "OR"
    return top["items"]


def _recently(branch, field, value, start_date):
    (when,) = [item for item in branch["items"] if isinstance(item, dict)]
    changed, filed = when["items"]
    return (
        when["join"] == "OR"
        and changed["join"] == "AND"
        and set(changed["items"])
        == {
            (False, field, "changedto", value),
            (False, field, "changedafter", start_date),
        }
        and filed == (False, "creation_ts", "greaterthan", start_date)
    )


def test_a_pending_impact_request_qualifies_in_any_product():
    rule = _rule()
    params = rule.get_bz_params(DATE)
    start_date, _ = rule.get_dates(DATE)
    impact, _ = _branches(params)
    assert impact["join"] == "AND"
    assert (False, "cf_performance_impact", "equals", "?") in impact["items"]
    assert _recently(impact, "cf_performance_impact", "?", start_date)
    assert not any(
        isinstance(c, tuple) and c[1] in ("product", "component")
        for c in impact["items"]
    )


def test_a_bug_in_the_triaged_component_qualifies():
    rule = _rule()
    params = rule.get_bz_params(DATE)
    start_date, _ = rule.get_dates(DATE)
    _, moved = _branches(params)
    product, component = TRIAGED_COMPONENT
    assert (False, "product", "equals", product) in moved["items"]
    assert (False, "component", "equals", component) in moved["items"]
    assert _recently(moved, "component", component, start_date)


def test_skips_bugs_hackbot_has_commented_on():
    chart = _chart(_rule().get_bz_params(DATE))
    assert (True, "commenter", "equals", HACKBOT_EMAIL) in chart


def test_queries_only_open_bugs_in_named_products():
    rule = _rule()
    params = rule.get_bz_params(DATE)
    assert params["resolution"] == "---"
    assert rule.has_default_products() is False
    assert "product" not in params and "component" not in params


# --- triggering the agent ----------------------------------------------- #


@pytest.fixture
def triggered(monkeypatch):
    monkeypatch.setenv("HACKBOT_API_URL", "https://hackbot.example")
    calls = []

    def fake_trigger(agent, inputs, dedupe_key=None):
        calls.append((agent, inputs, dedupe_key))
        return f"run-{inputs['bug_id']}"

    monkeypatch.setattr("bugbot.rules.perf_triage.trigger_agent_run", fake_trigger)
    return calls


def _bugs(*ids):
    return {str(i): _bug(REPORTER_MAIL, bug_id=i) for i in ids}


def test_dry_run_triggers_nothing_but_still_reports(triggered):
    rule = _rule(dryrun=True)
    bugs = rule.trigger_runs(_bugs(1, 2))
    assert triggered == []
    assert set(bugs) == {"1", "2"}
    assert rule.organize(bugs)


def test_triggers_one_deduplicated_run_per_bug(triggered):
    # The dedupe key is what stops a bug reset to `?` after the agent rated it,
    # or one that outlived the cache, from being rated again.
    rule = _rule(dryrun=False)
    bugs = rule.trigger_runs(_bugs(1, 2))
    assert triggered == [
        ("perf-triage", {"bug_id": 1}, "perf-triage:1"),
        ("perf-triage", {"bug_id": 2}, "perf-triage:2"),
    ]
    assert bugs["1"]["run_id"] == "run-1"


def test_caps_the_number_of_runs(triggered):
    rule = _rule(dryrun=False, max_triggers=2)
    bugs = rule.trigger_runs(_bugs(1, 2, 3, 4))
    assert len(triggered) == 2
    assert set(bugs) == {"1", "2"}
    assert rule.left_for_next_run == 2


def test_blanked_api_url_fails_the_rule_up_front(monkeypatch):
    monkeypatch.setenv("HACKBOT_API_URL", "")
    with pytest.raises(ValueError, match="HACKBOT_API_URL"):
        _rule(dryrun=False).trigger_runs(_bugs(1))


def test_a_failing_trigger_does_not_stop_the_others(triggered, monkeypatch):
    def flaky(agent, inputs, dedupe_key=None):
        if inputs["bug_id"] == 1:
            raise RuntimeError("hackbot down")
        return f"run-{inputs['bug_id']}"

    monkeypatch.setattr("bugbot.rules.perf_triage.trigger_agent_run", flaky)
    rule = _rule(dryrun=False)
    assert set(rule.trigger_runs(_bugs(1, 2))) == {"2"}
    assert rule.left_for_next_run == 1


# --- the email report --------------------------------------------------- #


def _render(rule, bugs):
    env = Environment(loader=FileSystemLoader("templates"))
    return env.get_template(rule.template()).render(
        date=DATE,
        data=rule.organize(bugs),
        extra=rule.get_extra_for_template(),
        str=str,
        enumerate=enumerate,
        plural=utils.plural,
        no_manager=rule.no_manager,
        table_attrs="",
    )


def test_template_renders_a_row_per_triaged_bug(triggered):
    rule = _rule(dryrun=False, max_triggers=1)
    html = _render(rule, rule.trigger_runs(_bugs(1, 2)))
    assert "show_bug.cgi?id=1" in html
    assert "Core :: Performance: General" in html
    assert "perf-triage agent" in html
    assert "1</b> more bug" in html
