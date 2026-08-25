# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from jinja2 import Environment, FileSystemLoader

from bugbot import hackbot_utils, utils
from bugbot.rules.frontend_triage import TRIAGED_COMPONENTS, FrontendTriage

# Who filed a bug no longer decides anything in Python -- Bugzilla does the
# `editbugs` filtering server-side -- so the reporter is now just a value the
# report has to carry.
REPORTER_MAIL = "reporter@example.org"


def _rule(**over):
    rule = FrontendTriage()
    for key, value in over.items():
        setattr(rule, key, value)
    return rule


def _bug(creator, bug_id=1):
    return {
        "id": bug_id,
        "summary": "New Tab weather widget vanishes",
        "creator": creator,
        # `bughandler` copies these into the row because the rule sets
        # `has_product_component()`, so they have to be here or it raises KeyError.
        "product": "Firefox",
        "component": "New Tab Page",
        # `amend_bzparams` adds `groups` to include_fields for every rule, and
        # `get_summary` reads it to redact security bugs.
        "groups": [],
    }


# --- who gets triaged --------------------------------------------------- #


def test_keeps_a_human_filed_bug():
    assert _rule().handle_bug(_bug(REPORTER_MAIL), {}) is not None


def test_drops_a_bot_filed_bug():
    # Bots hold `editbugs`, so the query lets them through and this is the only
    # thing stopping them. Both addresses are real: over the 30 days to
    # 2026-08-25 these two filed 9 of the 106 bugs the query matched in the
    # triaged components, all machine-generated alerts the agent would have
    # commented on unattended. The IAM roster used to drop them by not listing
    # them. One covers `utils.is_bot_email`'s `.tld` arm, the other its `.bugs`.
    rule = _rule()
    assert rule.handle_bug(_bug("performance-sheriff-bot@mozilla.tld"), {}) is None
    assert rule.handle_bug(_bug("intermittent-bug-filer@mozilla.bugs"), {}) is None


def test_reporter_reaches_the_report():
    # `bughandler` rebuilds each row from scratch and keeps only id/summary, so
    # anything else a column needs has to be stashed in `data` (the idiom in
    # rules/defectenhancementtask.py). Going through `bughandler` rather than
    # `handle_bug` is what catches that.
    rule = _rule(dryrun=True)
    rule.cache.set_dry_run(True)
    data: dict = {}
    rule.bughandler(_bug(REPORTER_MAIL), data)
    assert data["1"]["creator"] == REPORTER_MAIL
    # And every column the template reads is present, so organize() won't raise.
    assert set(rule.columns()) <= set(data["1"]) | {"run_id"}


# --- which bugs are queried --------------------------------------------- #


def test_does_not_use_the_default_product_list():
    # The query names Firefox itself; inheriting the 19-product default list
    # would triage the whole tree.
    assert _rule().has_default_products() is False


def _queried_pairs(params):
    """Reconstruct the `(product, component)` pairs from the boolean chart.

    Walks the numbered fields instead of asserting on `f7`/`v7` by name, so the
    test still means something if the numbering shifts.
    """
    pairs = []
    pending: dict = {}
    for i in range(1, 100):
        field = params.get(f"f{i}")
        if field is None:
            continue
        if field == "OP":
            pending = {}
        elif field == "CP":
            if {"product", "component"} <= pending.keys():
                pairs.append((pending["product"], pending["component"]))
            pending = {}
        elif field in ("product", "component"):
            assert params[f"o{i}"] == "equals"
            pending[field] = params[f"v{i}"]
    return pairs


def test_queries_every_triaged_component():
    params = _rule().get_bz_params("2026-07-28")
    assert _queried_pairs(params) == list(TRIAGED_COMPONENTS)


def test_pairs_a_component_with_its_own_product():
    # The regression this guards: `{"product": [...], "component": [...]}` would
    # return the same bugs today, because Bugzilla matches the two fields
    # independently and no cross pairing happens to exist -- and would silently
    # widen the day somebody creates `Toolkit :: Installer`.
    params = _rule().get_bz_params("2026-07-28")
    assert "product" not in params
    assert "component" not in params


def test_ors_the_component_groups_and_ands_within_each():
    params = _rule().get_bz_params("2026-07-28")
    opens = [i for i in range(1, 100) if params.get(f"f{i}") == "OP"]
    assert params[f"j{opens[0]}"] == "OR"
    assert [params[f"j{i}"] for i in opens[1:]] == ["AND"] * len(TRIAGED_COMPONENTS)


def test_spans_more_than_one_product():
    # Not a tautology on the tuple: it is why the query needs groups at all, so if
    # the scope ever narrows back to one product this test should be revisited
    # rather than the groups being left in place unexplained.
    assert len({product for product, _ in TRIAGED_COMPONENTS}) > 1


def test_queries_only_open_defects():
    params = _rule().get_bz_params("2026-07-28")
    assert params["bug_type"] == "defect"
    assert params["resolution"] == "---"


def _clauses(params):
    """The `(field, operator, value)` triples in the chart, whatever they're numbered.

    `OP`/`CP` carry no operator or value, so the numbering is not dense and the
    real clauses have to be picked out by which indexes have an `o`.
    """
    return {
        (params[f"f{i}"], params[f"o{i}"], params[f"v{i}"])
        for i in range(1, 100)
        if f"o{i}" in params
    }


def test_queries_only_recently_filed_bugs():
    rule = _rule()
    params = rule.get_bz_params("2026-07-28")
    start_date, _ = rule.get_dates("2026-07-28")
    assert ("creation_ts", "greaterthan", start_date) in _clauses(params)


def test_queries_only_reporters_with_editbugs():
    # The agent's analysis lands on the bug unattended, so the rule is limited to
    # reporters Bugzilla already trusts with bug metadata. `spambug.py:52` and
    # `stepstoreproduce.py:32` use the same pronoun in its negative form to find
    # the reporters this one leaves out.
    params = _rule().get_bz_params("2026-07-28")
    assert ("reporter", "substring", "%group.editbugs%") in _clauses(params)


def test_ands_the_reporter_check_with_the_component_groups():
    # The regression this guards: inside the OR group, the reporter check would
    # gate only the one component branch it landed in and leave the other eight
    # open to any reporter at all. Checks the property rather than the index, so
    # putting the clause after the group instead of before it still passes.
    params = _rule().get_bz_params("2026-07-28")
    reporter = [i for i in range(1, 100) if params.get(f"f{i}") == "reporter"]
    assert len(reporter) == 1
    group = [i for i in range(1, 100) if params.get(f"f{i}") in ("OP", "CP")]
    assert reporter[0] < min(group) or reporter[0] > max(group)


def test_requests_the_fields_the_report_needs():
    # `creator` is no longer read by any filter -- Bugzilla does the `editbugs`
    # check server-side -- but the report still has a Reporter column.
    params = _rule().get_bz_params("2026-07-28")
    assert {"id", "summary", "creator"} <= set(params["include_fields"])


# --- triggering the agent ----------------------------------------------- #


@pytest.fixture
def triggered(monkeypatch):
    """Capture the runs the rule would trigger, instead of calling hackbot."""
    monkeypatch.setenv("HACKBOT_API_URL", "https://hackbot.example")
    calls = []

    def fake_trigger(agent, inputs):
        calls.append((agent, inputs))
        return f"run-{inputs['bug_id']}"

    monkeypatch.setattr("bugbot.rules.frontend_triage.trigger_agent_run", fake_trigger)
    return calls


def _bugs(*ids):
    return {str(i): _bug(REPORTER_MAIL, bug_id=i) for i in ids}


def test_dry_run_triggers_nothing(triggered):
    rule = _rule(dryrun=True)
    rule.trigger_runs(_bugs(1, 2))
    assert triggered == []


def test_dry_run_still_reports_which_bugs_it_would_have_triaged(triggered):
    # The dry run is how a human checks the filter before enabling the cron, so
    # it has to survive `organize()`, which does a bare lookup of every column.
    rule = _rule(dryrun=True)
    bugs = rule.trigger_runs(_bugs(1, 2))
    assert set(bugs) == {"1", "2"}
    assert rule.organize(bugs)


def test_triggers_one_run_per_bug(triggered):
    rule = _rule(dryrun=False)
    rule.trigger_runs(_bugs(1, 2))
    assert triggered == [
        ("frontend-triage", {"bug_id": 1}),
        ("frontend-triage", {"bug_id": 2}),
    ]


def test_records_the_run_id_on_each_bug(triggered):
    rule = _rule(dryrun=False)
    bugs = rule.trigger_runs(_bugs(1))
    assert bugs["1"]["run_id"] == "run-1"


def test_caps_the_number_of_runs(triggered):
    # Each run is real LLM spend, so a flood of filings must not turn into a
    # flood of agent runs.
    rule = _rule(dryrun=False, max_triggers=2)
    bugs = rule.trigger_runs(_bugs(1, 2, 3, 4))
    assert len(triggered) == 2
    # Only the bugs actually triaged are reported, so the cap isn't silent.
    assert set(bugs) == {"1", "2"}
    assert rule.left_for_next_run == 2


def test_reports_nothing_skipped_when_under_the_cap(triggered):
    rule = _rule(dryrun=False)
    rule.trigger_runs(_bugs(1, 2))
    assert rule.get_extra_for_template() == {"left_for_next_run": 0}


def test_defaults_to_the_production_api(monkeypatch):
    # No env var needed on the cron host: the deployment is at a stable custom
    # domain, so it can be the default (as BUGBUG_HTTP_SERVER's is).
    monkeypatch.delenv("HACKBOT_API_URL", raising=False)
    assert hackbot_utils.api_url() == "https://hackbot-api.moz.tools"


def test_env_var_overrides_the_default(monkeypatch):
    monkeypatch.setenv("HACKBOT_API_URL", "https://hackbot-api-staging.example")
    assert hackbot_utils.api_url() == "https://hackbot-api-staging.example"


def test_explicitly_blanked_api_url_fails_the_rule_up_front(monkeypatch):
    # Deliberately pointing at nothing is a misconfiguration, not a transient
    # failure. Failing once before the loop keeps it from looking like N flaky
    # triggers, and lets the cron error digest surface it.
    monkeypatch.setenv("HACKBOT_API_URL", "")
    attempts = []
    monkeypatch.setattr(
        "bugbot.rules.frontend_triage.trigger_agent_run",
        lambda agent, inputs: attempts.append(inputs),
    )

    rule = _rule(dryrun=False)
    with pytest.raises(ValueError, match="HACKBOT_API_URL"):
        rule.trigger_runs(_bugs(1, 2))
    assert attempts == []


def test_a_failing_trigger_does_not_stop_the_others(triggered, monkeypatch):
    def flaky(agent, inputs):
        if inputs["bug_id"] == 1:
            raise RuntimeError("hackbot down")
        triggered.append((agent, inputs))
        return f"run-{inputs['bug_id']}"

    monkeypatch.setattr("bugbot.rules.frontend_triage.trigger_agent_run", flaky)

    rule = _rule(dryrun=False)
    bugs = rule.trigger_runs(_bugs(1, 2))
    assert triggered == [("frontend-triage", {"bug_id": 2})]
    # The bug we failed to trigger is not reported as triaged, so it stays out
    # of the cache and gets another chance on the next run.
    assert set(bugs) == {"2"}
    # And the report says so, rather than quietly losing it.
    assert rule.left_for_next_run == 1


# --- the email report --------------------------------------------------- #


def _render(rule, bugs):
    env = Environment(loader=FileSystemLoader("templates"))
    return env.get_template(rule.template()).render(
        date="2026-07-28",
        data=rule.organize(bugs),
        extra=rule.get_extra_for_template(),
        str=str,
        enumerate=enumerate,
        plural=utils.plural,
        no_manager=rule.no_manager,
        table_attrs="",
    )


def test_template_renders_a_row_per_triaged_bug(triggered):
    # The email path is otherwise only exercised in production, where a template
    # typo would be a silent 500 in the cron log.
    rule = _rule(dryrun=False)
    html = _render(rule, rule.trigger_runs(_bugs(1, 2)))
    assert "show_bug.cgi?id=1" in html
    assert "show_bug.cgi?id=2" in html
    assert REPORTER_MAIL in html
    assert "run-1" in html
    # With three products in scope, the summary alone no longer says what a row is
    # about. This also catches the template's positional unpacking going stale
    # against `columns()`.
    assert "Firefox :: New Tab Page" in html


def test_template_reports_the_bugs_left_for_next_run(triggered):
    rule = _rule(dryrun=False, max_triggers=1)
    html = _render(rule, rule.trigger_runs(_bugs(1, 2, 3)))
    assert "2</b> more bugs" in html
    assert "next run" in html


def test_template_omits_the_cap_note_when_it_does_not(triggered):
    rule = _rule(dryrun=False)
    html = _render(rule, rule.trigger_runs(_bugs(1)))
    assert "more bug" not in html
