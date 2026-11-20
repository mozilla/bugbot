# Rule scenarios

A scenario is a set of bugs and the expected outcome of running a rule on them.
Every `tests/scenarios/<rule>/<name>.yaml` file is a test (see
`tests/test_scenarios.py`):

```sh
uv run pytest tests/test_scenarios.py                    # all the scenarios
uv run pytest tests/test_scenarios.py -k uplift_beta     # the scenarios of a rule
```

The rule runs unmodified, as `BzCleaner.run` would (`must_run`, `has_enough_data`,
`get_email_data`, rendering the email) but against an in-memory Bugzilla
(`tests/framework/fake_bugzilla.py`) which evaluates the rule's searches on the
scenario's bugs: a scenario tests the queries of the rule as well as its Python
code. Everything else is mocked as well: the time is frozen, the Firefox
versions and the people directory come from the scenario, and any other HTTP
request fails unless the scenario mocks it.

## Writing a scenario

```yaml
description: >
  The assignee of a bug fixed in nightly and affecting beta is asked for an
  uplift decision, unless the bug caused a regression which isn't fixed yet.
  The regressions themselves don't match the query.
now: 2026-11-10T08:00:00Z
versions: {nightly: 162, beta: 161, release: 160, esr: 153}
release_schedule:
  beta: {release: 2026-11-24 14:00:00+00:00}
bugs:
  - id: 1
    assigned_to: dev@mozilla.com
    cf_status_firefox162: fixed
    cf_status_firefox161: affected
    attachments: [{file_name: phabricator-D1001-url.txt}]
  - id: 2
    regressed_by: [1]  # Bug 1 gets `regressions: [2]` automatically.
  - id: 3
    ...
expect:
  email: [3]
  changes:
    3:
      flags: [{name: needinfo, requestee: dev@mozilla.com}]
      comment: {body: !contains "[D1003](https://lando.moz.tools/D1003/)"}
```

The rule is the directory name (`workflow.p1` for `bugbot/rules/workflow/p1.py`,
or `rule: module:ClassName` when the module has several rules).

### Bugs

Only `id` is required. The other fields default to an open, unassigned `Core ::
General` defect filed at `now` (see `BUG_DEFAULTS` in `tests/framework/bugs.py`),
and the status/tracking flags of `versions` are `---`. Also:

- `*_detail` fields (`assigned_to_detail`, `cc_detail`...) are derived from the
  emails, using `users` when they're defined there;
- relations are mirrored: `regressed_by`/`regressions`, `depends_on`/`blocks` and
  `dupe_of`/`duplicates`;
- `comments` (strings, or dicts), `history` and `attachments` are served by
  their endpoints, and as fields when requested with `include_fields`. Their
  items get defaults too (ids, author, time...), and so do the `flags`.

Dates are kept as strings, as Bugzilla returns them: `2026-11-10T08:00:00Z`
doesn't need quotes.

### Searches

The fake Bugzilla evaluates the searches (`tests/framework/search.py`) with the
semantics of BMO's `Bugzilla/Search.pm`, quirks included. Some to be aware of
when writing bugs for a query:

- string comparisons are case insensitive, except `casesubstring`;
- on fields with several values (keywords, flags, depends_on, attachments...),
  `notequals`, `nowords`... mean that *no* value matches;
- but `longdesc` (comments) conditions match if *any* comment matches, even with
  `notsubstring`: rules use the negation (`n1: 1`) to mean "no comment matches";
- empty custom datetime fields (e.g. `cf_last_resolved`) count as 1970;
- relative dates (`-2w`, `1ds`) are relative to `now`;
- the default `creation_time` and `last_change_time` of the bugs is `now`.

So a bug only goes through the rule if it matches its query, like on Bugzilla:
make the scenario include bugs that *don't* match, to test the query. Use
`show` (see below) to see which bugs each search matched.

The evaluator only supports what the rules use, and fails on anything else
(field, operator, parameter, pronoun...) with `UnsupportedSearch`. If your
rule needs something new, add it to `tests/framework/search.py` following
`Search.pm` (https://github.com/mozilla-bteam/bmo/blob/master/Bugzilla/Search.pm),
with a test in `tests/test_search.py`. Recording a scenario (see below) checks
the evaluator against Bugzilla for the recorded bugs. `InvalidSearch` means that
Bugzilla itself would reject the search.

### Everything else

| Key | Description |
| --- | --- |
| `now` | The frozen current time, also the default run date. |
| `date` | The `--date` the rule runs with, `today` by default. |
| `versions` | `nightly`, `beta`, `release`, `esr` (and `esr_previous`). |
| `release_schedule` | The whattrainisitnow schedules, keyed by channel or version. |
| `users` | Bugzilla users (`name` is the email). Undefined users are active. |
| `people` | Entries of `configs/people.json`, empty by default (needed by nag rules). |
| `components` | `Product::Component` to `default_assigned_to`, `triage_owner`, `team_name`... |
| `config` | Overrides of the rule's entries in `configs/rules.json`. |
| `rule_args`, `rule_attrs` | Constructor arguments, and attributes set after it. |
| `http` | Other responses: `{url, json or body, method, status}`. |
| `render_email` | Render the email, `true` by default (catches template errors). |

### Expectations

| Key | Description |
| --- | --- |
| `email` | The bugs in the email: a list of ids, or ids mapped to (a subset of) their rows. |
| `changes` | (A subset of) the changes sent to Bugzilla, by bug. Bugs not listed must not change. |
| `nags` | For nag rules, the bug ids each person is nagged about. |
| `silent` | The bugs changed without sending bugmail. |
| `created` | (A subset of) the bugs created. |
| `email_contains` | Strings that the rendered email must contain. |
| `ran` | `false` if the rule should decide not to run (e.g. `must_run`). |

Unspecified expectations are not checked. Dicts are compared on the expected
keys only: `null` means that the key must be absent, `!any` that it must be
present, and `!contains text` matches any string containing `text`. Lists and
other values must be equal.

To see the actual outcome of a scenario (e.g. to write its expectations):

```sh
uv run python -m tests.framework.show tests/scenarios/uplift_beta/open_regression.yaml [--rows] [--email]
```

Scenarios can also be used inline, from regular tests:

```python
from tests.framework.scenario import assert_scenario

result = assert_scenario({"rule": "uplift_beta", "bugs": [...], "expect": {...}})
```

## Recording a scenario from real bugs

```sh
uv run python -m tests.framework.record uplift_beta --find 5         # bugs currently matching
uv run python -m tests.framework.record uplift_beta 2084355 2083531 --name assignee_asked
```

The rule runs against the real Bugzilla, with its searches restricted to the
given bugs. Nothing is written (changes are intercepted, other non-GET requests
are blocked) and no email is sent. The bugs it fetched are saved with all their
data (the queries can depend on any field), with everything else it fetched,
the time and the versions. Then:

- each search of the rule is run again on Bugzilla, restricted to the recorded
  bugs, and compared with the fake Bugzilla's evaluation;
- the scenario is replayed against the fake Bugzilla to write its expectations,
  and compared with the live run.

Any difference is printed, and the recorder exits with status 2: the scenario
or the fake Bugzilla (often the evaluation of searches) is missing something.
If a bug fetched by the rule (e.g. a regressor) also matches its searches, it is
recorded as one of the bugs to run the rule on, since the replay will consider
it too.

The data the outcome doesn't depend on is then removed: a field is dropped when
the replay stays exactly the same without it (same outcome, same bugs matched
by each search, and same lines of BugBot executed so that bugs aren't skipped
for another reason). The fields
the rule explicitly asks for in `include_fields` are always kept. Use
`--no-minimize` to keep everything.

Options:

- `--people`: include the `configs/people.json` entries of the people involved
  (nag rules need them). This is not public data: review or anonymize it;
- `--attr NAME=JSON`: set an attribute on the rule;
- `-D DATE`, `--description`, `-o PATH` (`-` for stdout), `--force`.

Private bugs are never recorded, private comments and attachments are dropped.
Recorded bugs are real bugs: the expectations record what the rule did at that
time. Bugs the rule already acted on usually don't match its query any more:
edit them back to their previous state (see their `history`), or to explore
variants.
