# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Regression tests for the AssigneeNoLogin rule's priority-change lookup.

The production fix changed ``change["field_name"]`` and ``change["added"]`` to
``change.get("field_name")`` and ``change.get("added")`` in
``bugbot/rules/assignee_no_login.py:get_priority_change_date``. These tests
exercise both the pre-fix failure mode (a KeyError when history entries are
missing one of the expected keys) and the fixed behaviour.
"""

from datetime import datetime

from bugbot.rules.assignee_no_login import AssigneeNoLogin


def _make_rule():
    return AssigneeNoLogin()


def test_get_priority_change_date_returns_date_when_history_entry_matches():
    rule = _make_rule()
    when = "2024-01-15T12:00:00Z"
    bug = {
        "priority": "P1",
        "history": [
            {"field_name": "priority", "added": "P3", "when": "2023-01-01T00:00:00Z"},
            {"field_name": "priority", "added": "P1", "when": when},
        ],
    }

    result = rule.get_priority_change_date(bug)

    assert result == datetime(2024, 1, 15, 12, 0, 0)


def test_get_priority_change_date_handles_missing_field_name_without_keyerror():
    """A history entry without ``field_name`` must not crash the lookup."""
    rule = _make_rule()
    when = "2024-05-20T08:30:00Z"
    bug = {
        "priority": "P2",
        "history": [
            # Missing both "field_name" and "added" - this is what crashed
            # before the fix.
            {"when": "2024-04-01T00:00:00Z"},
            {"field_name": "status", "added": "NEW", "when": "2024-04-15T00:00:00Z"},
            {"field_name": "priority", "added": "P2", "when": when},
        ],
    }

    result = rule.get_priority_change_date(bug)

    assert result == datetime(2024, 5, 20, 8, 30, 0)


def test_get_priority_change_date_returns_none_when_no_match():
    rule = _make_rule()
    bug = {
        "priority": "P1",
        "history": [
            {"field_name": "priority", "added": "P2", "when": "2024-01-01T00:00:00Z"},
            {
                "field_name": "status",
                "added": "RESOLVED",
                "when": "2024-02-01T00:00:00Z",
            },
        ],
    }

    assert rule.get_priority_change_date(bug) is None


def test_get_priority_change_date_skips_entries_missing_field_name():
    """Entries that lack ``field_name`` must be skipped, not raise KeyError."""
    rule = _make_rule()
    bug = {
        "priority": "P1",
        "history": [
            # No "field_name" key at all.
            {"added": "P1", "when": "2024-03-10T00:00:00Z"},
        ],
    }

    # Should not raise KeyError. The fixed implementation falls back to None
    # when the field_name check fails (None != "priority").
    assert rule.get_priority_change_date(bug) is None


def test_get_priority_change_date_picks_most_recent_match():
    rule = _make_rule()
    bug = {
        "priority": "P3",
        "history": [
            {"field_name": "priority", "added": "P1", "when": "2023-06-01T00:00:00Z"},
            {"field_name": "priority", "added": "P2", "when": "2024-02-01T00:00:00Z"},
            {"field_name": "priority", "added": "P3", "when": "2024-08-15T00:00:00Z"},
        ],
    }

    result = rule.get_priority_change_date(bug)

    assert result == datetime(2024, 8, 15, 0, 0, 0)
