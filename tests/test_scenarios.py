# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Run every scenario of `tests/scenarios/<rule>/*.yaml`."""

import os

import pytest

from tests.framework.scenario import (
    SCENARIOS_DIR,
    check,
    discover_scenarios,
    load_scenario,
    run_scenario,
)

PATHS = discover_scenarios()


@pytest.mark.parametrize(
    "path", PATHS, ids=[os.path.relpath(p, SCENARIOS_DIR) for p in PATHS]
)
def test_scenario(path):
    scenario = load_scenario(path)
    errors = check(run_scenario(scenario), scenario.expect)
    assert not errors, "Unexpected outcome:\n  " + "\n  ".join(errors)
