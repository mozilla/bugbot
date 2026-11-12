# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Scenario-based testing for BugBot rules.

A scenario is a set of bugs (and optionally users, people, versions and
arbitrary HTTP responses) plus the expected outcome of running a rule on them.
The rule runs unmodified against an in-memory Bugzilla (see `fake_bugzilla`),
which evaluates its searches (see `search`), so its queries, extra fetches and
Python filtering are all exercised.

See `tests/scenarios/README.md` for the scenario format.
"""
