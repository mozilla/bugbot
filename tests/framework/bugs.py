# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Turn the terse bug/user definitions of a scenario into full Bugzilla objects.

Scenarios only spell out the fields that matter for the test; everything else
gets a sensible default here, so that rules reading a field the scenario did
not mention still see what Bugzilla would return.
"""

import copy
import re
import zlib
from typing import Any

NOBODY = "nobody@mozilla.org"
DEFAULT_REPORTER = "reporter@example.com"
DEFAULT_TIME = "2026-01-01T00:00:00Z"

# Fields with a static default value.
BUG_DEFAULTS: dict[str, Any] = {
    "alias": None,
    "assigned_to": NOBODY,
    "blocks": [],
    "cc": [],
    "cf_last_resolved": None,
    "classification": "Components",
    "component": "General",
    "creator": DEFAULT_REPORTER,
    "depends_on": [],
    "dupe_of": None,
    "duplicates": [],
    "flags": [],
    "groups": [],
    "keywords": [],
    "mentors": [],
    "op_sys": "Unspecified",
    "platform": "Unspecified",
    "priority": "--",
    "product": "Core",
    "qa_contact": "",
    "regressed_by": [],
    "regressions": [],
    "resolution": "",
    "see_also": [],
    "severity": "--",
    "status": "NEW",
    "target_milestone": "---",
    "type": "defect",
    "url": "",
    "version": "unspecified",
    "votes": 0,
    "whiteboard": "",
    "is_confirmed": True,
    "is_cc_accessible": True,
    "is_creator_accessible": True,
    "comment_count": 0,
    "deadline": None,
    "actual_time": 0,
    "estimated_time": 0,
    "remaining_time": 0,
    # The custom fields of all the products.
    "cf_a11y_review_project_flag": "---",
    "cf_accessibility_severity": "---",
    "cf_cab_review": "---",
    "cf_crash_signature": "",
    "cf_fx_iteration": "---",
    "cf_fx_points": "---",
    "cf_has_str": "---",
    "cf_performance_impact": "---",
    "cf_qa_whiteboard": "",
    "cf_rank": None,
    "cf_user_story": "",
    "cf_webcompat_priority": "---",
    "cf_webcompat_score": "---",
}

# Fields holding an email, and the `_detail` field Bugzilla derives from it.
USER_FIELDS = {
    "assigned_to": "assigned_to_detail",
    "creator": "creator_detail",
    "qa_contact": "qa_contact_detail",
    "triage_owner": "triage_owner_detail",
}
USER_LIST_FIELDS = {"cc": "cc_detail", "mentors": "mentors_detail"}

# Pairs of fields that Bugzilla keeps in sync between two bugs.
SYMMETRIC_RELATIONS = [
    ("depends_on", "blocks"),
    ("blocks", "depends_on"),
    ("regressed_by", "regressions"),
    ("regressions", "regressed_by"),
]

# Not real bug fields: served through their own endpoints (and as bug fields
# when explicitly requested with `include_fields`).
SIDE_DATA = ("comments", "history", "attachments")


def user_id(email: str) -> int:
    return zlib.crc32(email.encode()) % 1_000_000 + 1


def make_user(email: str, overrides: dict | None = None, now: str = DEFAULT_TIME):
    """A Bugzilla user object. Unknown users are active, regular accounts."""
    nick = email.split("@")[0]
    user = {
        "id": user_id(email),
        "name": email,
        "email": email,
        "real_name": f"{nick} [:{nick}]",
        "nick": nick,
        "can_login": True,
        "creation_time": "2020-01-01T00:00:00Z",
        "last_activity_time": now,
        "last_seen_date": now,
        "groups": [],
    }
    if email == NOBODY:
        user["real_name"] = "Nobody; OK to take it and work on it"
    user.update(overrides or {})
    return user


def make_detail(email: str, users: dict) -> dict:
    # Users may have been fetched with only some fields.
    user = make_user(email, users.get(email))
    return {
        "id": user["id"],
        "name": email,
        "email": email,
        "real_name": user["real_name"],
        "nick": user["nick"],
        "active": user["can_login"],
    }


def _status_default(field: str):
    """Default for the per-version flags, which exist for any version."""
    if field.startswith(("cf_status_", "cf_tracking_")):
        return "---"
    return None


def missing_field_default(field: str):
    return _status_default(field)


def version_flags(versions: dict | None) -> list[str]:
    """The status and tracking flags of the current versions."""
    if not versions:
        return []
    numbers = {versions.get(c) for c in ("release", "beta", "nightly", "central")}
    esrs = {versions.get(c) for c in ("esr", "esr_previous")}
    return [
        f"cf_{kind}_firefox{prefix}{v}"
        for prefix, values in (("", numbers), ("_esr", esrs))
        for v in sorted(v for v in values if v is not None)
        for kind in ("status", "tracking")
    ]


def normalize_bug(
    bug: dict, users: dict, now: str, versions: dict | None = None
) -> dict:
    """Fill a scenario bug with the defaults and derived fields."""
    assert "id" in bug, f"Bug without an id: {bug}"
    bug = copy.deepcopy(bug)
    bug["id"] = int(bug["id"])
    creation = bug.setdefault("creation_time", now)

    for field, value in BUG_DEFAULTS.items():
        bug.setdefault(field, copy.deepcopy(value))
    for name in version_flags(versions):
        bug.setdefault(name, "---")
    bug.setdefault("summary", f"Bug {bug['id']}")
    bug.setdefault("last_change_time", now)
    bug.setdefault("is_open", bug["status"] not in ("RESOLVED", "VERIFIED", "CLOSED"))

    for field, detail in USER_FIELDS.items():
        if bug.get(field):
            bug.setdefault(detail, make_detail(bug[field], users))
    for field, detail in USER_LIST_FIELDS.items():
        bug.setdefault(detail, [make_detail(email, users) for email in bug[field]])

    for i, flag in enumerate(bug["flags"]):
        flag.setdefault("id", bug["id"] * 100 + i)
        flag.setdefault("type_id", 800)
        flag.setdefault("status", "?")
        flag.setdefault("setter", bug["creator"])
        flag.setdefault("creation_date", creation)
        flag.setdefault("modification_date", flag["creation_date"])

    if "comments" in bug:
        bug["comments"] = [
            _normalize_comment(bug, i, comment)
            for i, comment in enumerate(bug["comments"])
        ]
    if "history" in bug:
        for entry in bug["history"]:
            entry.setdefault("who", bug["creator"])
            entry.setdefault("when", creation)
            for change in entry.setdefault("changes", []):
                change.setdefault("added", "")
                change.setdefault("removed", "")
    if "attachments" in bug:
        for i, attachment in enumerate(bug["attachments"]):
            _normalize_attachment(bug, i, attachment)

    return bug


def _normalize_comment(bug: dict, count: int, value: str | dict) -> dict:
    comment = {"text": value} if isinstance(value, str) else dict(value)
    comment.setdefault("count", count)
    comment.setdefault("id", bug["id"] * 1000 + comment["count"])
    comment.setdefault("bug_id", bug["id"])
    comment.setdefault("author", bug["creator"])
    comment.setdefault("creator", comment["author"])
    comment.setdefault("time", bug["creation_time"])
    comment.setdefault("creation_time", comment["time"])
    comment.setdefault("text", "")
    comment.setdefault("raw_text", comment["text"])
    comment.setdefault("is_private", False)
    comment.setdefault("attachment_id", None)
    comment.setdefault("tags", [])
    return comment


def _normalize_attachment(bug: dict, i: int, attachment: dict) -> None:
    attachment.setdefault("id", bug["id"] * 100 + i)
    attachment.setdefault("bug_id", bug["id"])
    attachment.setdefault("creator", bug["creator"])
    attachment.setdefault("creation_time", bug["creation_time"])
    attachment.setdefault("last_change_time", attachment["creation_time"])
    attachment.setdefault("summary", f"Attachment {attachment['id']}")
    attachment.setdefault("description", attachment["summary"])
    attachment.setdefault("file_name", f"attachment-{attachment['id']}.txt")
    attachment.setdefault(
        "content_type",
        "text/x-phabricator-request"
        if re.fullmatch(r"phabricator-D\d+-url\.txt", attachment["file_name"])
        else "text/plain",
    )
    attachment.setdefault("is_obsolete", 0)
    attachment.setdefault("is_patch", 0)
    attachment.setdefault("is_private", 0)
    attachment.setdefault("flags", [])


def link_bugs(bugs: dict[int, dict]) -> None:
    """Mirror the relations between bugs, as Bugzilla does.

    Declaring `regressed_by: [2]` on bug 1 is enough for bug 2 to list bug 1 in
    its `regressions` (same for `depends_on`/`blocks`, and `dupe_of` for
    `duplicates`). Relations to bugs outside the scenario are kept as-is.
    """
    for bug in bugs.values():
        for field, reverse in SYMMETRIC_RELATIONS:
            for other_id in bug[field]:
                other = bugs.get(int(other_id))
                if other is not None and bug["id"] not in other[reverse]:
                    other[reverse] = sorted(other[reverse] + [bug["id"]])
        if bug["dupe_of"]:
            target = bugs.get(int(bug["dupe_of"]))
            if target is not None and bug["id"] not in target["duplicates"]:
                target["duplicates"] = sorted(target["duplicates"] + [bug["id"]])


def strip_defaults(bug: dict, users: dict, now: str) -> dict:
    """Inverse of `normalize_bug`: drop what it would add back on its own.

    Used when recording scenarios, to keep the generated files readable.
    """
    bug = copy.deepcopy(bug)
    for field, default in BUG_DEFAULTS.items():
        if bug.get(field, object()) == default:
            del bug[field]
    if bug.get("summary") == f"Bug {bug['id']}":
        del bug["summary"]

    all_users = {**USER_FIELDS, **USER_LIST_FIELDS}
    for field, detail in all_users.items():
        if detail not in bug:
            continue
        value: Any = bug.get(field, BUG_DEFAULTS.get(field))
        expected: Any
        if field in USER_LIST_FIELDS:
            expected = [make_detail(email, users) for email in value or []]
        else:
            expected = make_detail(value, users) if value else None
        if bug[detail] == expected:
            del bug[detail]

    if "is_open" in bug:
        status = bug.get("status", BUG_DEFAULTS["status"])
        if bug["is_open"] == (status not in ("RESOLVED", "VERIFIED", "CLOSED")):
            del bug["is_open"]

    for key in list(bug):
        if bug[key] is not None and bug[key] == missing_field_default(key):
            del bug[key]

    return bug
