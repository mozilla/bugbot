# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from bugbot import constants, utils
from bugbot import reo_regressions as reo
from bugbot.bzcleaner import BzCleaner
from bugbot.rules.reo_regression_slack import ReoRegressionSlack
from bugbot.rules.reo_regression_slack_daily import ReoRegressionSlackDaily

# Both messages, for the behaviour they share as `BzCleaner` rules. What one of
# them does on its own is in its own test file.
RULES = (ReoRegressionSlack, ReoRegressionSlackDaily)


def test_regressions_query_without_a_split_asks_for_the_whole_set():
    query = reo.regressions_query(150)

    assert query["f1"] == "cf_status_firefox150"
    assert query["v1"] == "affected"
    # No condition on the previous version, so neither side of the split.
    assert "f2" not in query
    assert "n2" not in query


def test_regressions_query_new_looks_at_the_previous_version():
    query = reo.regressions_query(150, carry_over=False)

    assert query["j2"] == "OR"
    assert query["f3"] == query["f4"] == query["f5"] == "cf_status_firefox149"
    assert {query["v3"], query["v4"], query["v5"]} == {"unaffected", "?", "---"}
    assert "n2" not in query


def test_regressions_query_carry_over_negates_the_whole_group():
    new = reo.regressions_query(150, carry_over=False)
    carry_over = reo.regressions_query(150, carry_over=True)

    # The two partition the set, so the only difference between them is the
    # negation, and it has to sit on the OP at f2 rather than on the first
    # condition inside the group.
    assert carry_over == {**new, "n2": "1"}
    assert carry_over["f2"] == "OP"


@pytest.mark.parametrize("carry_over", (None, False, True))
def test_the_regressions_query_drops_the_excluded_products(carry_over):
    # The burndown query is the other one that has to, and its own test covers it.
    query = reo.regressions_query(150, carry_over)
    excluded = {
        query[f"v{n}"]
        for n in range(
            reo.EXCLUDED_PRODUCTS_SLOT,
            reo.EXCLUDED_PRODUCTS_SLOT + len(reo.EXCLUDED_PRODUCTS),
        )
        if query.get(f"f{n}") == "product"
    }

    assert excluded == set(reo.EXCLUDED_PRODUCTS)


def test_each_excluded_product_gets_its_own_condition():
    # Not one nowords: Bugzilla splits that value on whitespace, so
    # "Developer Infrastructure" would match as two separate words and drop
    # products nobody asked to exclude.
    conditions = reo.without_excluded_products()

    assert len(conditions) == 3 * len(reo.EXCLUDED_PRODUCTS)
    assert all(
        op == "notequals" for key, op in conditions.items() if key.startswith("o")
    )
    assert any(
        " " in v for k, v in conditions.items() if k.startswith("v")
    ), "the multi-word product is what makes the per-product split necessary"


def test_the_exclusion_slots_clear_every_other_slot_in_use():
    # with_severities takes 11, and the burndown's uplift flag takes 11 too, so
    # the exclusions have to start above both.
    query = reo.with_severities(reo.regressions_query(150), ("S1", "S2"))
    used = {int(k[1:]) for k in query if k[0] in "fov" and k[1:].isdigit()}
    assert reo.EXCLUDED_PRODUCTS_SLOT > max(
        n for n in used if n < reo.EXCLUDED_PRODUCTS_SLOT
    )


def test_flag_names_come_from_get_flag():
    # utils.get_flag is the one place version numbers become flag names; these
    # queries must not concatenate their own.
    query = reo.regressions_query(150, carry_over=False)

    assert query["f1"] == utils.get_flag(150, "status", "release")
    assert query["f8"] == utils.get_flag(150, "tracking", "release")
    assert query["f3"] == utils.get_flag(149, "status", "release")


def test_the_shared_fields_ask_for_the_groups_field():
    # Without it no message can tell a restricted bug from a public one, and both
    # rules build their field lists out of this one.
    assert "groups" in reo.BUG_FIELDS.split(",")


def test_the_shared_fields_never_ask_for_a_bug_summary():
    # A restricted bug is counted and linked, never named, and not asking for the
    # field is what makes that true of anything built on this list.
    assert "summary" not in reo.BUG_FIELDS.split(",")


def test_restricted_note_counts_bugs_in_any_group():
    bugs = [
        {"id": 1, "groups": ["core-security-release"]},
        {"id": 2, "groups": ["mozilla-employee-confidential"]},
        {"id": 3, "groups": []},
    ]

    # Wider than the `bug_group ~ "sec"` branch in the daily rule's burndown query
    # on purpose: the note explains why the linked list looks short, and any group
    # does that.
    assert reo.restricted_note(bugs) == " (2 restricted)"


@pytest.mark.parametrize("bugs", ([], [{"id": 1, "groups": []}]))
def test_restricted_note_is_silent_when_nothing_is_restricted(bugs):
    assert reo.restricted_note(bugs) == ""


LONG_LIST = [{"id": 1000000 + i} for i in range(300)]
SHORT_URL = "https://bugzilla.mozilla.org/1a2b3c"


def test_bug_link_shortens_a_snapshot_that_is_too_long(monkeypatch):
    # The shortener is preferred over the fallback query: it still points at
    # exactly the bugs counted, where a live query can drift from the count.
    monkeypatch.setattr(reo.utils, "shorten_long_bz_url", lambda url: SHORT_URL)

    link = reo.bug_link(LONG_LIST, "{} New Regressions", {"resolution": "---"})

    assert link == f"<{SHORT_URL}|300 New Regressions>"


def test_bug_link_shortens_a_team_line_that_has_no_fallback(monkeypatch):
    # Team lines pass no fallback, as reproducing a team as a query means listing
    # all of its components, so before the shortener they lost their link entirely.
    monkeypatch.setattr(reo.utils, "shorten_long_bz_url", lambda url: SHORT_URL)

    assert reo.bug_link(LONG_LIST, "{} Media") == f"<{SHORT_URL}|300 Media>"


def test_bug_link_rejects_the_multiline_shortener_fallback(monkeypatch):
    # utils.shorten_long_bz_url answers a shortener error with the URL split over
    # lines (bugbot#1402). A Slack link would end at the first newline, so that has
    # to count as a failure and drop through to the query.
    monkeypatch.setattr(
        reo.utils, "shorten_long_bz_url", lambda url: "https://a\nhttps://b"
    )

    link = reo.bug_link(LONG_LIST, "{} New Regressions", {"resolution": "---"})

    assert "buglist.cgi?resolution=---" in link
    assert "\n" not in link


def test_bug_link_survives_a_shortener_that_raises(monkeypatch):
    def boom(url):
        raise RuntimeError("shortener down")

    monkeypatch.setattr(reo.utils, "shorten_long_bz_url", boom)

    link = reo.bug_link(LONG_LIST, "{} New Regressions", {"resolution": "---"})

    assert "buglist.cgi?resolution=---" in link


def test_bug_link_is_left_unlinked_when_nothing_works(monkeypatch):
    monkeypatch.setattr(
        reo.utils, "shorten_long_bz_url", lambda url: "https://a\nhttps://b"
    )

    assert reo.bug_link(LONG_LIST, "{} Media") == "300 Media"


def test_bug_link_does_not_shorten_a_url_that_fits(monkeypatch):
    def unexpected(url):
        raise AssertionError("a short URL should never reach the shortener")

    monkeypatch.setattr(reo.utils, "shorten_long_bz_url", unexpected)

    assert reo.bug_link([{"id": 1}], "{} Media") == (
        "<https://bugzilla.mozilla.org/buglist.cgi?bug_id=1&order=bug_list|1 Media>"
    )


def test_to_blocks_wraps_each_section_on_its_own():
    assert reo.to_blocks(["one", "two"]) == [
        {"type": "section", "text": {"type": "mrkdwn", "text": "one"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "two"}},
    ]


def test_to_blocks_refuses_to_post_an_overflowing_section():
    with pytest.raises(RuntimeError, match="over the 3000 limit"):
        reo.to_blocks(["x" * (reo.SECTION_LIMIT + 1)])


def test_block_text_reads_every_block_shape():
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "Title"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "Daily update"}]},
        {"type": "section", "text": {"type": "mrkdwn", "text": "Body"}},
    ]

    assert [reo.block_text(block) for block in blocks] == [
        "Title",
        "Daily update",
        "Body",
    ]


@pytest.mark.parametrize("rule_class", RULES)
def test_both_messages_are_bzcleaner_rules(rule_class):
    # The searches, the arguments, the must_run gate and the error handling are
    # the framework's; what these two add is where the report goes.
    assert isinstance(rule_class(), BzCleaner)


@pytest.mark.parametrize("rule_class", RULES)
def test_a_query_goes_out_as_the_rule_built_it(rule_class):
    rule = rule_class()
    params = {**reo.regressions_query(150), "include_fields": reo.BUG_FIELDS}
    rule.amend_bzparams(params, [])

    # No `summary`: a restricted bug is counted and linked, never named.
    assert params["include_fields"] == reo.BUG_FIELDS
    # No default product list, no [no-nag] exclusion and no group filter. The
    # query is bugdash's, and what it matches is what gets counted.
    assert "product" not in params
    assert "[no-nag]" not in params.values()
    assert "bug_group" not in params.values()


@pytest.mark.parametrize("rule_class", RULES)
def test_neither_message_caches_the_bugs_it_reports(rule_class):
    # A bug belongs in these messages until somebody acts on it, so the cache
    # that keeps other rules from repeating themselves has to stay off. It is by
    # default -- `max_days_in_cache` is -1 -- and this is what would catch a
    # configs/rules.json entry turning it on.
    rule = rule_class()
    rule.cache.set_dry_run(False)  # as a --production run does

    assert rule.max_days_in_cache() < 1
    assert 1234 not in rule.cache


@pytest.mark.parametrize("rule_class", RULES)
def test_the_report_is_a_slack_message_rather_than_an_email(rule_class, monkeypatch):
    posted = []
    rule = rule_class()
    rule.dryrun = False
    rule.test_mode = False
    monkeypatch.setattr(reo, "versions_to_report", lambda: {})
    monkeypatch.setattr(rule, "blocks", lambda versions: ["a block"])
    monkeypatch.setattr(
        reo.slack,
        "post_to_slack",
        lambda channel, text, blocks=None: posted.append((channel, text, blocks))
        or "1.0",
    )

    # The empty list is what stops `send_email` sending anything.
    assert rule.get_email_data("today") == []

    (channel, text, blocks), *rest = posted
    assert not rest
    assert (channel, blocks) == (reo.CHANNEL, ["a block"])
    assert text, "the message needs its notification fallback text"


def test_high_severity_is_the_shared_constant():
    # Shared with the rest of bugbot rather than the REO queries' ("S1", "S2"), so
    # the legacy names count too.
    assert reo.HIGH_SEVERITY is constants.HIGH_SEVERITY
    assert {"S1", "S2", "critical", "major", "blocker"} <= reo.HIGH_SEVERITY


def test_with_severities_builds_a_stable_url():
    # HIGH_SEVERITY is a set, and set iteration order is not stable across
    # processes, so the value has to be sorted or the URL changes run to run.
    query = reo.with_severities({"resolution": "---"}, reo.HIGH_SEVERITY)

    assert query["v11"] == ", ".join(sorted(reo.HIGH_SEVERITY))
    assert query["o11"] == "anyexact"
