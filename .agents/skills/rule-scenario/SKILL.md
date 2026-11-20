---
name: rule-scenario
description: Create a test scenario for a BugBot rule, from real Bugzilla bugs (recorded) or from a description of the situation to test (hand-written). Use when asked to add a test/scenario for a rule, to reproduce what a rule did (or should have done) on some bugs, or to turn a bug report about a rule into a regression test.
---

# Creating a rule scenario

Scenarios live in `tests/scenarios/<rule>/<name>.yaml` and run with
`uv run pytest tests/test_scenarios.py -k <name>`. Read
`tests/scenarios/README.md` for the format before writing or editing one.

## 1. Figure out the inputs

- **Rule**: the module under `bugbot/rules/` (`uplift_beta`, or `workflow.p1` for
  a subdirectory). Read the rule to know what it queries, fetches, and changes.
- **Bugs**: the ids given by the user. If they only describe a situation, either
  find matching bugs with
  `uv run python -m tests.framework.record <rule> --find 10`, or write the
  scenario by hand (step 3).
- **What should happen**: what the user expects the rule to do on these bugs.
  If they reported the rule misbehaving, the scenario must expect the *correct*
  behaviour, so the test fails until the rule is fixed.

## 2. Record it

```sh
uv run python -m tests.framework.record <rule> <bug> [<bug> ...] \
    --name <short_snake_case_name> --description "<what this checks>"
```

- Run it from the repository root. It needs network access to Bugzilla (no
  API key needed for public bugs; private bugs are refused).
- Nothing is written to Bugzilla: changes are intercepted and other non-GET
  requests are blocked. If a rule needs a blocked request, mock it by hand in
  the scenario's `http`.
- The outcome is printed. If it is empty because the bugs don't match the rule's
  queries any more (e.g. the rule already acted on them), record with
  `--no-minimize`, edit the bugs back to the state before the rule acted (their
  `history` says what changed), re-run `show`, and minimize by hand. Explain
  this in the description.
- Rules with `must_run` only run on some weekdays: pass `-D <a matching date>`.
- Nag rules need `--people`. That data comes from `configs/people.json` and is
  not public: replace names/emails with placeholders (consistently in the whole
  file, then re-check the outcome with `show`) unless the user says otherwise.
- **Exit status 2** means the fake Bugzilla differs from the real one: either
  its evaluation of a search disagrees with Bugzilla's results, or the replay
  differs from the live run (a missing HTTP resource, or a Bugzilla endpoint or
  behaviour the fake doesn't emulate). Investigate and fix the gap: in
  `tests/framework/search.py` for searches (following BMO's `Search.pm`, with a
  test in `tests/test_search.py`), in `tests/framework/fake_bugzilla.py`, or in
  the scenario. Don't commit a scenario whose expectations don't match reality.
- `UnsupportedSearch` means the rule's query uses something the evaluator
  doesn't support yet: add it the same way. `InvalidSearch` means Bugzilla
  itself rejects the query: that's a bug in the rule, tell the user.

## 3. Or write it by hand

Start from the smallest scenario: only the fields the rule (and its query)
reads, everything else has defaults. Use linked bugs (`regressed_by`,
`depends_on`, `dupe_of`) when the rule fetches related bugs. The rule's
searches are evaluated on the bugs, so read its `get_bz_params` (and the
"Searches" section of the README for BMO's quirks), and add bugs that should
*not* match to test the query. Then look at the actual outcome:

```sh
uv run python -m tests.framework.show tests/scenarios/<rule>/<name>.yaml --rows --searches
```

## 4. Review the expectations

The recorder writes the outcome as a snapshot. Don't trust it blindly:

- Check that it is what the rule *should* do. If it isn't, tell the user: either
  the rule has a bug (keep the correct expectation, the test should fail), or
  the scenario misses some data.
- Make the expectations about the point of the scenario: trim long comment
  bodies to the meaningful part with `!contains`, and drop expectations that are
  irrelevant to what's tested. Keep `changes` explicit about which bugs change
  (bugs not listed must not change).
- Write a real `description`, and give the file a name that says what it tests.
- Recorded bugs are real public bugs: it's fine to edit them to create variants
  (e.g. copy the file, change a status flag, and adjust the expectations).

## 5. Verify

```sh
uv run pytest tests/test_scenarios.py -k <name>
uv run pre-commit run --files tests/scenarios/<rule>/<name>.yaml
```

Also break the scenario on purpose once (e.g. change a field the outcome
depends on) to make sure it fails, then revert.
