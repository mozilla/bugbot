# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict

import pytest

from bugbot.rules.web_platform_features import (
    FeatureBugUpdate,
    InteropBug,
    UpdateInterop,
)

INTEROP_URL = "https://github.com/web-platform-tests/interop/issues/{}"


def run_interop(proposals, user_story=None, updates=None):
    """Run UpdateInterop.update() for a single bug.

    proposals is {interop issue: year}, user_story the parsed user story."""
    rule = UpdateInterop.__new__(UpdateInterop)
    if updates is None:
        updates = defaultdict(FeatureBugUpdate)
    rule.update(
        updates,
        {
            1: [
                InteropBug(user_story if user_story is not None else {}, issue, year)
                for issue, year in proposals.items()
            ]
        },
    )
    return updates[1]


@pytest.mark.parametrize(
    "existing, user_story, proposals, expected",
    [
        # No entry yet
        ("web-feature:foo", {}, {11: 2026}, "web-feature:foo\ninterop-proposal:2026"),
        # Already recorded, nothing to do
        ("interop-proposal:2026", {"interop-proposal": "2026"}, {11: 2026}, None),
        # Add a year to an existing entry
        (
            "interop-proposal:2024",
            {"interop-proposal": "2024"},
            {11: 2026},
            "interop-proposal:2024,2026",
        ),
        # Existing entry already lists several years
        (
            "interop-proposal:2024,2025",
            {"interop-proposal": "2024,2025"},
            {11: 2026},
            "interop-proposal:2024,2025,2026",
        ),
        # Whitespace around the stored value must still match
        (
            "interop-proposal: 2025",
            {"interop-proposal": " 2025 "},
            {11: 2026},
            "interop-proposal:2025,2026",
        ),
        # Several proposals, no entry yet: one merged entry, not one per proposal
        (
            "web-feature:foo",
            {},
            {11: 2025, 22: 2026},
            "web-feature:foo\ninterop-proposal:2025,2026",
        ),
        # Several proposals merged into an existing entry
        (
            "interop-proposal:2024",
            {"interop-proposal": "2024"},
            {11: 2025, 22: 2026},
            "interop-proposal:2024,2025,2026",
        ),
        # Several proposals, one of them already recorded
        (
            "interop-proposal:2025",
            {"interop-proposal": "2025"},
            {11: 2025, 22: 2026},
            "interop-proposal:2025,2026",
        ),
    ],
)
def test_interop_user_story(existing, user_story, proposals, expected):
    update = run_interop(proposals, user_story)
    assert update.update_user_story(existing) == expected
    if expected is None:
        assert update.user_story == []


def test_interop_user_story_idempotent():
    """A second pass over the rule's own output must be a no-op."""
    first = run_interop({11: 2025, 22: 2026}).update_user_story("web-feature:foo")
    assert first == "web-feature:foo\ninterop-proposal:2025,2026"

    second = run_interop({11: 2025, 22: 2026}, {"interop-proposal": "2025,2026"})
    assert second.user_story == []
    assert second.update_user_story(first) is None


def test_interop_user_story_non_year_value():
    """A non-year value is left alone rather than merged into."""
    update = run_interop({11: 2026}, {"interop-proposal": "accepted"})
    assert (
        update.update_user_story("interop-proposal:accepted")
        == "interop-proposal:accepted\ninterop-proposal:2026"
    )


def test_interop_user_story_multiple_entries():
    """With several entries the year list is the one that gets updated."""
    update = run_interop({11: 2026}, {"interop-proposal": ["accepted", "2024"]})
    assert (
        update.update_user_story("interop-proposal:accepted\ninterop-proposal:2024")
        == "interop-proposal:accepted\ninterop-proposal:2024,2026"
    )


def test_interop_see_also():
    update = run_interop({11: 2025, 22: 2026})
    assert update.see_also == {
        INTEROP_URL.format(11): True,
        INTEROP_URL.format(22): True,
    }
    # Links already on the bug are not added again, whether in see_also or url
    assert not update.update_see_also(
        "", [INTEROP_URL.format(11), INTEROP_URL.format(22)]
    )
    assert not update.update_see_also(INTEROP_URL.format(11), [INTEROP_URL.format(22)])
    assert update.update_see_also("", [INTEROP_URL.format(11)]).to_json() == {
        "add": [INTEROP_URL.format(22)]
    }


def test_interop_preserves_see_also_from_other_rules():
    """UpdateInterop runs after UpdateMetadata on a shared FeatureBugUpdate."""
    updates = defaultdict(FeatureBugUpdate)
    updates[1].see_also["https://example.com/keep/"] = True
    updates[1].see_also["https://example.com/drop/"] = False

    update = run_interop({11: 2026}, updates=updates)

    assert update.see_also == {
        "https://example.com/keep/": True,
        "https://example.com/drop/": False,
        INTEROP_URL.format(11): True,
    }
