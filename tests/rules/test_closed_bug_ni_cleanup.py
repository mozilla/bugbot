# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from bugbot.bzcleaner import BzCleaner
from bugbot.rules.closed_bug_ni_cleanup import ClosedBugNiCleanup

CHANGED_AT = "2026-08-10T12:00:00Z"
BEFORE_CHANGE = "2026-08-10T11:59:59Z"
AFTER_CHANGE = "2026-08-10T12:00:01Z"


def _flag(flag_id, modified_at, created_at=None):
    return {
        "id": flag_id,
        "name": "needinfo",
        "status": "?",
        "requestee": "user@example.com",
        "creation_date": created_at or modified_at,
        "modification_date": modified_at,
    }


@pytest.mark.parametrize(
    "resolution,product,run_date",
    [
        ("WONTFIX", "Firefox", "2026-10-16"),
        ("DUPLICATE", "Firefox", "2026-08-11"),
        ("FIXED", "Firefox Graveyard", "2026-10-16"),
        ("", "Firefox Graveyard", "2026-10-16"),
    ],
)
def test_cleanup_preserves_needinfos_set_after_eligibility_change(
    monkeypatch, resolution, product, run_date
):
    moved = product.endswith("Graveyard")
    bug = {
        "id": 123,
        "product": product,
        "resolution": resolution,
        "cf_last_resolved": "2026-07-01T12:00:00Z" if moved else CHANGED_AT,
        "dupe_of": 456 if resolution == "DUPLICATE" else None,
        "flags": [
            _flag(1, BEFORE_CHANGE),
            _flag(2, CHANGED_AT),
            _flag(3, AFTER_CHANGE),
            _flag(4, AFTER_CHANGE, created_at=BEFORE_CHANGE),
        ],
    }
    if moved:
        bug["history"] = [
            {
                "when": "2026-07-10T12:00:00Z",
                "changes": [{"field_name": "product", "added": product}],
            },
            {
                "when": "2026-07-11T12:00:00Z",
                "changes": [{"field_name": "product", "added": "Firefox"}],
            },
            {
                "when": CHANGED_AT,
                "changes": [{"field_name": "product", "added": product}],
            },
            {
                "when": AFTER_CHANGE,
                "changes": [{"field_name": "component", "added": "General"}],
            },
        ]

    target = {
        "id": 456,
        "resolution": "FIXED",
        "cf_last_resolved": "2026-07-20T12:00:00Z",
    }
    monkeypatch.setattr(BzCleaner, "get_bugs", lambda self, **kwargs: {"123": bug})
    monkeypatch.setattr(
        ClosedBugNiCleanup, "get_dupe_targets", lambda self, bugids: {"456": target}
    )

    rule = ClosedBugNiCleanup()
    rule.get_bugs(run_date)

    assert rule.autofix_changes["123"]["flags"] == [
        {"id": 1, "status": "X"},
        {"id": 2, "status": "X"},
    ]


def test_graveyard_bug_without_recorded_move_keeps_needinfos():
    rule = ClosedBugNiCleanup()
    bug = {
        "product": "Firefox Graveyard",
        "resolution": "",
        "flags": [_flag(1, BEFORE_CHANGE)],
        "history": [],
    }

    assert rule.get_needinfos_to_clear(bug) == ([], None)
