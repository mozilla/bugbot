# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from jinja2 import Environment, FileSystemLoader

from bugbot import hackbot_utils, utils
from bugbot.people import People
from bugbot.rules.frontend_triage import FrontendTriage

STAFF_MAIL = "staffer@mozilla.com"
QA_MAIL = "tester@mozilla.com"
# An employee who files from a personal Bugzilla account, which is why the filter
# reads the roster rather than the address.
STAFF_PERSONAL_MAIL = "staffer@example.net"


def _person(mail, bzmail=None, cn="A Staffer"):
    return {
        "mail": mail,
        "bugzillaEmail": bzmail or mail,
        "cn": cn,
        "dn": f"mail={mail},o=com,dc=mozilla",
        "ismanager": "FALSE",
        "isdirector": "FALSE",
        "title": "Engineer",
        "manager": {"cn": "A Manager", "dn": "mail=boss,o=com,dc=mozilla"},
    }


def _people():
    # `People` is normally loaded from configs/people.json, which is gitignored
    # and absent in CI, so the roster is injected here. QA are on the roster too,
    # now that they file from @mozilla.com addresses.
    return People(
        [
            _person(STAFF_MAIL),
            _person(QA_MAIL, cn="A Tester"),
            _person("staffer@mozilla.com.example", bzmail=STAFF_PERSONAL_MAIL),
        ]
    )


def _rule(**over):
    rule = FrontendTriage(people=_people())
    for key, value in over.items():
        setattr(rule, key, value)
    return rule


def _bug(creator, bug_id=1):
    return {
        "id": bug_id,
        "summary": "New Tab weather widget vanishes",
        "creator": creator,
        "component": "New Tab Page",
        # `amend_bzparams` adds `groups` to include_fields for every rule, and
        # `get_summary` reads it to redact security bugs.
        "groups": [],
    }


# --- who gets triaged --------------------------------------------------- #


def test_keeps_employee_filed_bug():
    rule = _rule()
    assert rule.handle_bug(_bug(STAFF_MAIL), {}) is not None


def test_keeps_qa_filed_bug():
    # QA are on the staff roster now that they file from @mozilla.com, so they
    # need no separate rule of their own.
    rule = _rule()
    assert rule.handle_bug(_bug(QA_MAIL), {}) is not None


def test_keeps_bug_from_an_employees_personal_bugzilla_account():
    # The roster maps a staffer's Bugzilla address to them, so an employee who
    # doesn't file under @mozilla.com is still in scope. This is what a check on
    # the address alone would miss.
    rule = _rule()
    assert rule.handle_bug(_bug(STAFF_PERSONAL_MAIL), {}) is not None


def test_drops_community_filed_bug():
    # The pilot is scoped to reporters we expect to file well; everyone else is
    # left to the humans.
    rule = _rule()
    assert rule.handle_bug(_bug("someone@example.org"), {}) is None


def test_drops_a_mozilla_com_address_that_is_not_on_the_roster():
    # The roster is the source of truth, not the domain: a @mozilla.com address
    # IAM doesn't know about (a bot, a departed account) is not triaged.
    rule = _rule()
    assert rule.handle_bug(_bug("automation@mozilla.com"), {}) is None


def test_reporter_reaches_the_report():
    # `bughandler` rebuilds each row from scratch and keeps only id/summary, so
    # anything else a column needs has to be stashed in `data` (the idiom in
    # rules/defectenhancementtask.py). Going through `bughandler` rather than
    # `handle_bug` is what catches that.
    rule = _rule(dryrun=True)
    rule.cache.set_dry_run(True)
    data: dict = {}
    rule.bughandler(_bug(STAFF_MAIL), data)
    assert data["1"]["creator"] == STAFF_MAIL
    # And every column the template reads is present, so organize() won't raise.
    assert set(rule.columns()) <= set(data["1"]) | {"run_id"}


# --- which bugs are queried --------------------------------------------- #


def test_does_not_use_the_default_product_list():
    # The query names Firefox itself; inheriting the 19-product default list
    # would triage the whole tree.
    assert _rule().has_default_products() is False


def test_queries_the_configured_product_and_components():
    params = _rule().get_bz_params("2026-07-28")
    assert params["product"] == ["Firefox"]
    assert params["component"] == ["New Tab Page"]


def test_queries_only_open_defects():
    params = _rule().get_bz_params("2026-07-28")
    assert params["bug_type"] == "defect"
    assert params["resolution"] == "---"


def test_queries_only_recently_filed_bugs():
    rule = _rule()
    params = rule.get_bz_params("2026-07-28")
    start_date, _ = rule.get_dates("2026-07-28")
    triplet = {
        (params[f"f{i}"], params[f"o{i}"], params[f"v{i}"])
        for i in range(1, 10)
        if f"f{i}" in params
    }
    assert ("creation_ts", "greaterthan", start_date) in triplet


def test_requests_the_fields_the_filter_needs():
    params = _rule().get_bz_params("2026-07-28")
    assert {"id", "summary", "creator", "component"} <= set(params["include_fields"])


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
    return {str(i): _bug(STAFF_MAIL, bug_id=i) for i in ids}


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
    assert STAFF_MAIL in html
    assert "run-1" in html


def test_template_reports_the_bugs_left_for_next_run(triggered):
    rule = _rule(dryrun=False, max_triggers=1)
    html = _render(rule, rule.trigger_runs(_bugs(1, 2, 3)))
    assert "2</b> more bugs" in html
    assert "next run" in html


def test_template_omits_the_cap_note_when_it_does_not(triggered):
    rule = _rule(dryrun=False)
    html = _render(rule, rule.trigger_runs(_bugs(1)))
    assert "more bug" not in html
