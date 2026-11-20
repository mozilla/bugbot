# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Evaluate Bugzilla searches on scenario bugs.

This mirrors the semantics of BMO's search (`Bugzilla/Search.pm`, and the REST
layer in `Bugzilla/API/V1/Bug.pm`), including its quirks, e.g.:

- string comparisons are case insensitive (MySQL collation), except for
  `casesubstring`;
- on fields with several values (keywords, depends_on, flags, attachments...),
  a positive operator matches if any value matches, and a negative one
  (`notequals`, `nowords`...) if no value matches the positive operator;
- `longdesc` (comments) conditions match if *any* comment matches, even with
  negative operators: use `n` (negation) to mean "no comment matches";
- empty custom datetime fields (e.g. `cf_last_resolved`) count as 1970;
- conditions with an empty value are ignored.

Only what the rules use is supported. Anything else raises `UnsupportedSearch`:
add it here (with a test in `tests/test_search.py`), following `Search.pm`.
"""

import datetime
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta


class UnsupportedSearch(AssertionError):
    def __init__(self, message: str):
        super().__init__(
            f"{message}. The fake Bugzilla can't evaluate this search: add "
            "support for it in tests/framework/search.py, following BMO's "
            "Bugzilla/Search.pm."
        )


class InvalidSearch(AssertionError):
    """A search that BMO itself would reject."""

    def __init__(self, message: str):
        super().__init__(f"Bugzilla would reject this search: {message}")


# REST API names to the names used by the search (`Bugzilla::Bug::FIELD_MAP`).
API_TO_SEARCH = {
    "blocks": "blocked",
    "creation_time": "creation_ts",
    "creator": "reporter",
    "depends_on": "dependson",
    "dupe_of": "dup_id",
    "id": "bug_id",
    "is_confirmed": "everconfirmed",
    "last_change_time": "delta_ts",
    "comment_count": "longdescs.count",
    "platform": "rep_platform",
    "regressions": "regresses",
    "severity": "bug_severity",
    "status": "bug_status",
    "summary": "short_desc",
    "type": "bug_type",
    "url": "bug_file_loc",
    "whiteboard": "status_whiteboard",
}
# The names of the fields in the history returned by the REST API.
SEARCH_TO_API = {v: k for k, v in API_TO_SEARCH.items()}
SEARCH_TO_API["bug_group"] = "groups"

# Old names, still accepted (`Search.pm`'s FIELD_MAP).
OLD_NAMES = {"changedin": "days_elapsed", "long_desc": "longdesc"}

# Parameters which aren't search criteria.
NON_CRITERIA = {
    "include_fields",
    "exclude_fields",
    "limit",
    "offset",
    "order",
    "count_only",
    "api_key",
    "Bugzilla_api_key",
    "query_format",
}

BUG_STATUSES = [
    "UNCONFIRMED",
    "NEW",
    "ASSIGNED",
    "REOPENED",
    "RESOLVED",
    "VERIFIED",
    "CLOSED",
]
OPEN_STATUSES = BUG_STATUSES[:4]

# Scalar fields: search name -> REST field.
SCALAR_FIELDS = {
    "bug_id": "id",
    "short_desc": "summary",
    "bug_status": "status",
    "resolution": "resolution",
    "product": "product",
    "component": "component",
    "classification": "classification",
    "bug_type": "type",
    "priority": "priority",
    "bug_severity": "severity",
    "op_sys": "op_sys",
    "rep_platform": "platform",
    "version": "version",
    "target_milestone": "target_milestone",
    "status_whiteboard": "whiteboard",
    "bug_file_loc": "url",
    "alias": "alias",
    "votes": "votes",
    "everconfirmed": "is_confirmed",
    "creation_ts": "creation_time",
    "delta_ts": "last_change_time",
    "dup_id": "dupe_of",
    "deadline": "deadline",
}
# Fields holding a single user.
USER_FIELDS = {
    "assigned_to": "assigned_to",
    "reporter": "creator",
    "qa_contact": "qa_contact",
    "triage_owner": "triage_owner",
}
# Fields with several values: search name -> function returning them.
MULTI_FIELDS: dict[str, Callable[[dict], list]] = {
    "keywords": lambda bug: bug.get("keywords", []),
    "blocked": lambda bug: bug.get("blocks", []),
    "dependson": lambda bug: bug.get("depends_on", []),
    "regressed_by": lambda bug: bug.get("regressed_by", []),
    "regresses": lambda bug: bug.get("regressions", []),
    "duplicates": lambda bug: bug.get("duplicates", []),
    "bug_group": lambda bug: bug.get("groups", []),
    "see_also": lambda bug: bug.get("see_also", []),
}
ATTACHMENT_FIELDS = {
    "attachments.mimetype": "content_type",
    "attachments.ispatch": "is_patch",
    "attachments.isobsolete": "is_obsolete",
    "attachments.isprivate": "is_private",
    "attachments.filename": "file_name",
    "attachments.description": "summary",
}


def _flags(bug: dict) -> list[dict]:
    flags = list(bug.get("flags", []))
    for attachment in bug.get("attachments", []):
        flags += attachment.get("flags", [])
    return flags


def _public_comments(bug: dict) -> list[dict]:
    return [c for c in bug.get("comments", []) if not c.get("is_private")]


# Fields holding several users (searched through another table).
USER_LIST_FIELDS: dict[str, Callable[[dict], list]] = {
    "cc": lambda bug: bug.get("cc", []),
    "bug_mentor": lambda bug: bug.get("mentors", []),
    "commenter": lambda bug: [c["author"] for c in _public_comments(bug)],
    "setters.login_name": lambda bug: [f.get("setter") for f in _flags(bug)],
    "requestees.login_name": lambda bug: [
        f["requestee"] for f in _flags(bug) if f.get("requestee")
    ],
    "attachments.submitter": lambda bug: [
        a["creator"] for a in bug.get("attachments", []) if not a.get("is_private")
    ],
}
COUNT_FIELDS: dict[str, Callable[[dict], int]] = {
    "cc_count": lambda bug: len(bug.get("cc", [])),
    "dupe_count": lambda bug: len(bug.get("duplicates", [])),
    "see_also_count": lambda bug: len(bug.get("see_also", [])),
    "keywords.count": lambda bug: len(bug.get("keywords", [])),
    "blocked.count": lambda bug: len(bug.get("blocks", [])),
    "dependson.count": lambda bug: len(bug.get("depends_on", [])),
    "regressed_by.count": lambda bug: len(bug.get("regressed_by", [])),
    "regresses.count": lambda bug: len(bug.get("regressions", [])),
    "attachments.count": lambda bug: len(
        [a for a in bug.get("attachments", []) if not a.get("is_private")]
    ),
    "longdescs.count": lambda bug: (
        len(_public_comments(bug)) if "comments" in bug else bug.get("comment_count", 0)
    ),
}
# The field whose history `changed*` operators look at, for the count fields.
COUNT_HISTORY = {
    "cc_count": "cc",
    "see_also_count": "see_also",
    "keywords.count": "keywords",
    "blocked.count": "blocks",
    "dependson.count": "depends_on",
    "regressed_by.count": "regressed_by",
    "regresses.count": "regressions",
}

NUMERIC_FIELDS = {"bug_id", "votes", "dup_id", "days_elapsed", "everconfirmed"}
NUMERIC_FIELDS |= set(COUNT_FIELDS)
NUMERIC_FIELDS |= {"blocked", "dependson", "regressed_by", "regresses", "duplicates"}
NUMERIC_FIELDS |= {"attachments.ispatch", "attachments.isobsolete"}
NUMERIC_FIELDS |= {"attachments.isprivate"}
DATETIME_FIELDS = {"creation_ts", "delta_ts", "cf_last_resolved"}
DATE_FIELDS = {"deadline"}
# Single select fields get their values as a list, others as a string split
# on commas (only matters for values with commas).
SELECT_FIELDS = {
    "bug_status",
    "resolution",
    "product",
    "component",
    "classification",
    "bug_type",
    "priority",
    "bug_severity",
    "op_sys",
    "rep_platform",
}

OPERATORS = {
    "equals",
    "notequals",
    "casesubstring",
    "substring",
    "substr",
    "notsubstring",
    "regexp",
    "notregexp",
    "lessthan",
    "lessthaneq",
    "greaterthan",
    "greaterthaneq",
    "anyexact",
    "anywordssubstr",
    "allwordssubstr",
    "nowordssubstr",
    "anywords",
    "allwords",
    "nowords",
    "everchanged",
    "changedbefore",
    "changedafter",
    "changedfrom",
    "changedto",
    "changedby",
    "isempty",
    "isnotempty",
}
NO_VALUE_OPERATORS = {"everchanged", "isempty", "isnotempty"}
CHANGED_OPERATORS = {
    "everchanged",
    "changedbefore",
    "changedafter",
    "changedfrom",
    "changedto",
    "changedby",
}
REVERSE = {
    "nowords": "anywords",
    "nowordssubstr": "anywordssubstr",
    "anywords": "nowords",
    "anywordssubstr": "nowordssubstr",
    "lessthan": "greaterthaneq",
    "lessthaneq": "greaterthan",
    "greaterthan": "lessthaneq",
    "greaterthaneq": "lessthan",
    "isempty": "isnotempty",
    "isnotempty": "isempty",
}


def reverse_operator(operator: str) -> str:
    if operator in REVERSE:
        return REVERSE[operator]
    if operator.startswith("not"):
        return operator[3:]
    return "not" + operator


def is_known_field(name: str) -> bool:
    return (
        name in SCALAR_FIELDS
        or name in USER_FIELDS
        or name in MULTI_FIELDS
        or name in ATTACHMENT_FIELDS
        or name in USER_LIST_FIELDS
        or name in COUNT_FIELDS
        or name.startswith("cf_")
        or name in {"flagtypes.name", "longdesc", "days_elapsed", "anything"}
    )


def search_criteria(params: dict[str, list[str]]) -> dict[str, list[str]]:
    """The parameters of a search which select the bugs."""

    def key(name):
        # Custom search parameters in order: f1, o1, v1, f2...
        match = re.fullmatch(r"([fovnj])(\d+)", name)
        return (
            (1, int(match.group(2)), "fovnj".index(match.group(1)))
            if match
            else (0, name, 0)
        )

    return {k: params[k] for k in sorted(params, key=key) if k not in NON_CRITERIA}


# Dates


EMPTY_DATETIME = datetime.datetime(1970, 1, 1)
RELATIVE_DATE = re.compile(r"^([+-])?(\d+)([hdwmy])(s?)$", re.IGNORECASE)


def parse_datetime(value) -> datetime.datetime | None:
    """A naive UTC datetime, as stored in Bugzilla's database."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        dt = value
    else:
        try:
            dt = date_parser.isoparse(str(value))
        except ValueError:
            try:
                dt = date_parser.parse(str(value))
            except (ValueError, OverflowError):
                raise UnsupportedSearch(f"Unsupported date {value!r}")
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


def sqlify_date(value: str, now: datetime.datetime) -> datetime.datetime:
    """`Search.pm`'s SqlifyDate: relative dates (`-2w`, `1ds`...) and others."""
    value = (value or "").strip()
    if value.lower() in ("", "now"):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if re.fullmatch(r"%\w+%", value):
        raise UnsupportedSearch(f"Unsupported date pronoun {value}")

    match = RELATIVE_DATE.match(value)
    if not match:
        return parse_datetime(value)  # type: ignore[return-value]

    sign, amount, unit, start_of = match.groups()
    amount = int(amount)
    if sign == "+":
        amount = -amount
    unit = unit.lower()
    start_of = bool(start_of) or amount == 0
    date = now
    if unit == "w":
        amount *= 7
        if start_of:
            amount += now.isoweekday()  # Perl's DateTime wday: Monday is 1.
        unit = "d"
    if unit == "d":
        date -= datetime.timedelta(days=amount)
        return date.replace(hour=0, minute=0, second=0) if start_of else date
    if unit == "h":
        date -= datetime.timedelta(hours=amount)
        return date.replace(minute=0, second=0) if start_of else date
    if unit == "m":
        date -= relativedelta(months=amount)
        return date.replace(day=1, hour=0, minute=0, second=0) if start_of else date
    date -= relativedelta(years=amount)
    return (
        date.replace(month=1, day=1, hour=0, minute=0, second=0) if start_of else date
    )


# Parsing the parameters into a tree of conditions


@dataclass
class Condition:
    field: str
    operator: str
    value: str
    # A list for the select fields, otherwise the same as `value`.
    all_values: list[str] | str
    negate: bool = False


@dataclass
class Clause:
    joiner: str = "AND"
    children: list = field(default_factory=list)
    negate: bool = False
    # `AND_G`: the conditions must match the same row (e.g. history entry).
    group: bool = False

    def add(self, child) -> None:
        self.children.append(child)


def _values(params: dict[str, list[str]], name: str) -> list[str]:
    values = params.get(name, [])
    return [v for v in values if v is not None]


def _first(params: dict[str, list[str]], name: str, default: str = "") -> str:
    values = _values(params, name)
    return values[0] if values else default


def _condition(field: str, operator: str, values: list[str] | str) -> Condition:
    field = OLD_NAMES.get(field, field)
    if operator not in OPERATORS:
        raise UnsupportedSearch(f"Unsupported operator {operator!r} (field {field})")
    if not is_known_field(field):
        raise UnsupportedSearch(f"Unsupported field {field!r}")
    if operator in NO_VALUE_OPERATORS:
        values = " "
    if isinstance(values, list):
        values = [v.strip() for v in values if v is not None and v.strip() != ""]
        value = ",".join(values)
    else:
        value = values
    return Condition(field, operator, value, values)


def parse(params: dict[str, list[str]]) -> Clause:
    """Turn the parameters of a REST search into a tree of conditions."""
    params = {k: list(v) for k, v in params.items() if k not in NON_CRITERIA}

    # REST layer (`Bugzilla/API/V1/Bug.pm`).
    if "description" in params:
        params["longdesc"] = params.pop("description")
        params["longdesc_initial"] = ["1"]
    params = {API_TO_SEARCH.get(k, k): v for k, v in params.items()}

    custom_ids = [int(k[1:]) for k in params if re.fullmatch(r"f\d+", k)]
    next_id = max(custom_ids, default=0) + 1

    def add_custom(field: str, operator: str, value: str) -> None:
        nonlocal next_id
        params[f"f{next_id}"] = [field]
        params[f"o{next_id}"] = [operator]
        params[f"v{next_id}"] = [value]
        next_id += 1

    for name in ("delta_ts", "creation_ts"):
        if name in params:
            add_custom(name, "greaterthaneq", params.pop(name)[0])
    for name in ("short_desc", "longdesc", "status_whiteboard", "bug_file_loc"):
        if name in params and f"{name}_type" not in params:
            params[f"{name}_type"] = ["allwordssubstr"]
    if "keywords" in params and "keywords_type" not in params:
        params["keywords_type"] = ["allwords"]
    for role in (
        "assigned_to",
        "reporter",
        "qa_contact",
        "triage_owner",
        "commenter",
        "cc",
    ):
        if role in params:
            add_custom(role, "anywordssubstr", " ".join(params.pop(role)))

    # `Search.pm`.
    if "bugidtype" in params:
        value = _first(params, "bugidtype")
        params["bug_id_type"] = ["nowords" if value == "exclude" else "anyexact"]
    for old, new in OLD_NAMES.items():
        if old in params:
            params[new] = params.pop(old)

    top = Clause()
    _parse_bug_status(params)
    _parse_resolution(params)
    _parse_basic_fields(params, top)
    _parse_email(params, top)
    _parse_chfield(params, top)
    top.add(_parse_custom_search(params))
    return top


def _parse_bug_status(params) -> None:
    if "bug_status" not in params:
        return
    if _first(params, "bug_status_type", "anyexact") != "anyexact":
        return
    statuses = _values(params, "bug_status")
    if "__open__" in statuses:
        statuses += OPEN_STATUSES
    if "__closed__" in statuses:
        statuses += BUG_STATUSES[4:]
    valid = sorted({s.strip() for s in statuses} & set(BUG_STATUSES))
    if "__all__" in statuses or len(valid) == len(BUG_STATUSES):
        del params["bug_status"]
    else:
        params["bug_status"] = valid


def _parse_resolution(params) -> None:
    # BMO drops the condition when all the resolutions are given, which never
    # happens in practice.
    pass


def _parse_basic_fields(params, clause: Clause) -> None:
    handled_elsewhere = {"longdesc_initial", "j_top", "chfield", "chfieldfrom"}
    handled_elsewhere |= {"chfieldto", "chfieldvalue", "bug_id_type"}
    for name in list(params):
        if (
            re.fullmatch(r"[fovnj]\d+", name)
            or re.fullmatch(
                r"email(type|assigned_to|reporter|cc|qa_contact|longdesc|bug_mentor)?\d+",
                name,
            )
            or (name.endswith("_type") and not is_known_field(name))
            or name in handled_elsewhere
        ):
            continue
        field = name
        if not is_known_field(field):
            # `.` are passed as `_` in the parameters (e.g. flagtypes_name).
            dotted = name.replace("_", ".", 1)
            if not is_known_field(dotted):
                raise UnsupportedSearch(f"Unsupported search parameter {name!r}")
            field = dotted
        values = [v for v in _values(params, name) if v != ""]
        if not values:
            continue
        operator = _first(params, f"{name}_type", "anyexact")
        if field in SELECT_FIELDS:
            clause.add(_condition(field, operator, values))
        else:
            clause.add(_condition(field, operator, ",".join(values)))


def _parse_email(params, clause: Clause) -> None:
    for name in params:
        match = re.fullmatch(r"email(\d+)", name)
        if not match:
            continue
        n = match.group(1)
        email = _first(params, name).strip()
        if not email:
            continue
        operator = _first(params, f"emailtype{n}", "equals")
        if operator == "exact":
            operator = "equals"
        or_clause = Clause("OR")
        for role in ("assigned_to", "reporter", "cc", "qa_contact", "bug_mentor"):
            if _first(params, f"email{role}{n}"):
                or_clause.add(_condition(role, operator, email))
        if _first(params, f"emaillongdesc{n}"):
            or_clause.add(_condition("commenter", operator, email))
        clause.add(or_clause)


def _parse_chfield(params, clause: Clause) -> None:
    date_from = _first(params, "chfieldfrom").strip().lower()
    date_to = _first(params, "chfieldto").strip().lower()
    date_from = "" if date_from == "now" else date_from
    date_to = "" if date_to == "now" else date_to
    fields = [
        "creation_ts" if f == "[Bug creation]" else f
        for f in _values(params, "chfield")
    ]
    value_to = _first(params, "chfieldvalue")
    if not (date_from or date_to or value_to):
        return
    if date_from:
        clause.add(_condition("delta_ts", "greaterthaneq", date_from))
    if date_to and not fields and not value_to:
        clause.add(_condition("delta_ts", "lessthaneq", date_to))
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", date_to):
        date_to += " 23:59:59"
    or_clause = Clause("OR")
    for field_name in fields:
        group = Clause(group=True)
        if value_to:
            group.add(_condition(field_name, "changedto", value_to))
        if date_from:
            group.add(_condition(field_name, "changedafter", date_from))
        if date_to:
            group.add(_condition(field_name, "changedbefore", date_to))
        or_clause.add(group)
    clause.add(or_clause)


def _new_clause(joiner: str, negate: bool) -> Clause:
    if joiner == "AND_G":
        return Clause("AND", negate=negate, group=True)
    if joiner not in ("", "AND", "OR"):
        raise InvalidSearch(f"Invalid joiner {joiner!r}")
    return Clause(joiner or "AND", negate=negate)


def _parse_custom_search(params) -> Clause:
    current = _new_clause(_first(params, "j_top"), False)
    stack: list[Clause] = []
    ids = sorted(int(k[1:]) for k in params if re.fullmatch(r"f\d+", k))
    for i in ids:
        field_name = _first(params, f"f{i}")
        negate = _first(params, f"n{i}") not in ("", "0")
        if field_name == "OP":
            clause = _new_clause(_first(params, f"j{i}"), negate)
            current.add(clause)
            stack.append(current)
            current = clause
            continue
        if field_name == "CP":
            if not stack:
                raise InvalidSearch(f"CP without OP (f{i})")
            current = stack.pop()
            continue
        operator = _first(params, f"o{i}")
        if not field_name or not operator:
            continue
        values = _values(params, f"v{i}")
        value: list[str] | str = (
            values if len(values) > 1 else (values[0] if values else "")
        )
        if operator in NO_VALUE_OPERATORS:
            value = " "
        if value == "" or value == []:
            continue
        condition = _condition(field_name, operator, value)
        condition.negate = negate
        current.add(condition)
    return stack[0] if stack else current


# Evaluation


def _casefold(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value).casefold()


POSIX_CLASSES = {
    "alnum": r"0-9A-Za-z",
    "alpha": r"A-Za-z",
    "digit": r"0-9",
    "lower": r"a-z",
    "upper": r"A-Z",
    "space": r"\s",
    "punct": r"!-/:-@\[-`{-~",
    "word": r"\w",
}


def _compile_regexp(pattern: str) -> re.Pattern:
    if "[[:<:]]" in pattern or "[[:>:]]" in pattern:
        raise InvalidSearch(
            f"MySQL 8 doesn't support the word boundaries [[:<:]] and [[:>:]] "
            f"(use \\b instead) in {pattern!r}"
        )
    for name, chars in POSIX_CLASSES.items():
        pattern = pattern.replace(f"[:{name}:]", chars)
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise UnsupportedSearch(f"Unsupported regexp {pattern!r}: {e}")


def _words(value: str) -> list[str]:
    return [w for w in re.split(r"[\s,]+", value) if w]


def _word_regexp(word: str) -> re.Pattern:
    return re.compile(
        r"(^|[^0-9A-Za-z])" + re.escape(word) + r"($|[^0-9A-Za-z])", re.IGNORECASE
    )


class _Context:
    def __init__(self, now: datetime.datetime, users: dict, longdesc_initial: bool):
        self.now = now
        self.users = users
        self.longdesc_initial = longdesc_initial

    def user_groups(self, email: str) -> set[str]:
        """The groups of a user: names, or objects as returned by the API."""
        groups = (self.users.get(email) or {}).get("groups", [])
        return {g["name"] if isinstance(g, dict) else g for g in groups}


def _compare_values(field: str, operator: str, actual, value: str, ctx: _Context):
    """Compare a single value of a field with the searched one, as SQL would."""
    if field in DATETIME_FIELDS or field in DATE_FIELDS:
        actual_dt = parse_datetime(actual) or EMPTY_DATETIME
        expected: datetime.datetime | None
        if RELATIVE_DATE.match(value.strip()) or value.strip().lower() == "now":
            expected = sqlify_date(value, ctx.now)
        else:
            expected = parse_datetime(value)
        if expected is None:
            raise UnsupportedSearch(f"Unsupported date {value!r} for {field}")
        if field in DATE_FIELDS:
            actual_dt = actual_dt.replace(hour=0, minute=0, second=0)
        return _compare(operator, actual_dt, expected)

    if field in NUMERIC_FIELDS and re.fullmatch(r"[+-]?\d+(\.\d+)?", value.strip()):
        number = float(actual) if actual not in (None, "") else 0.0
        return _compare(operator, number, float(value))

    return _compare(operator, _casefold(actual), value.casefold())


def _compare(operator: str, actual, expected) -> bool:
    if operator == "equals":
        return actual == expected
    if operator == "notequals":
        return actual != expected
    if operator == "lessthan":
        return actual < expected
    if operator == "lessthaneq":
        return actual <= expected
    if operator == "greaterthan":
        return actual > expected
    if operator == "greaterthaneq":
        return actual >= expected
    raise AssertionError(operator)


def _match_value(
    field: str, operator: str, actual, cond_value, all_values, ctx
) -> bool:
    """`Search.pm`'s OPERATORS, applied to a single value of a field."""
    if operator in ("equals", "notequals", "lessthan", "lessthaneq", "greaterthan"):
        return _compare_values(field, operator, actual, cond_value, ctx)
    if operator == "greaterthaneq":
        return _compare_values(field, operator, actual, cond_value, ctx)
    text = _casefold(actual)
    if operator == "casesubstring":
        return cond_value in ("" if actual is None else str(actual))
    if operator in ("substring", "substr"):
        return cond_value.casefold() in text
    if operator == "notsubstring":
        return cond_value.casefold() not in text
    if operator == "regexp":
        return bool(_compile_regexp(cond_value).search(text))
    if operator == "notregexp":
        return not _compile_regexp(cond_value).search(text)
    if operator == "anyexact":
        if isinstance(all_values, list):
            values = all_values
        else:
            values = [v.strip() for v in all_values.split(",") if v.strip()]
        if field == "resolution":
            values = ["" if v == "---" else v for v in values]
        if not values:
            return None  # type: ignore[return-value]
        return any(_compare_values(field, "equals", actual, v, ctx) for v in values)
    if operator in ("anywordssubstr", "allwordssubstr", "nowordssubstr"):
        words = _words(cond_value)
        if not words:
            return None  # type: ignore[return-value]
        found = [w.casefold() in text for w in words]
        if operator == "allwordssubstr":
            return all(found)
        return any(found) if operator == "anywordssubstr" else not any(found)
    if operator in ("anywords", "allwords", "nowords"):
        words = _words(cond_value)
        if not words:
            return None  # type: ignore[return-value]
        found = [bool(_word_regexp(w).search(text)) for w in words]
        if operator == "allwords":
            return all(found)
        return any(found) if operator == "anywords" else not any(found)
    if operator == "isempty":
        return actual in (None, "", 0) if field in DATETIME_FIELDS else text == ""
    if operator == "isnotempty":
        return not _match_value(field, "isempty", actual, cond_value, all_values, ctx)
    raise UnsupportedSearch(f"Unsupported operator {operator!r} for field {field!r}")


def _history_name(field_name: str) -> str:
    field_name = COUNT_HISTORY.get(field_name, field_name)
    return SEARCH_TO_API.get(field_name, field_name)


def _changes(bug: dict, field_name: str) -> list[dict]:
    """The history entries of a field, flattened: dicts with `when`, `who`,
    `added` and `removed`."""
    name = _history_name(field_name)
    rows = []
    for entry in bug.get("history", []):
        for change in entry.get("changes", []):
            if field_name == "anything" or change.get("field_name") == name:
                rows.append({**change, "when": entry["when"], "who": entry["who"]})
    return rows


def _match_change(cond: Condition, row: dict, ctx: _Context) -> bool:
    operator = cond.operator
    if operator == "everchanged":
        return True
    if operator in ("changedbefore", "changedafter"):
        when = parse_datetime(row["when"]) or EMPTY_DATETIME
        date = sqlify_date(cond.value, ctx.now)
        return when <= date if operator == "changedbefore" else when >= date
    if operator in ("changedfrom", "changedto"):
        column = "removed" if operator == "changedfrom" else "added"
        return _casefold(row.get(column)) == cond.value.casefold()
    if operator == "changedby":
        if re.fullmatch(r"%\w+%", cond.value):
            raise UnsupportedSearch(f"Unsupported pronoun {cond.value}")
        return _casefold(row["who"]) == cond.value.casefold()
    raise AssertionError(operator)


def _eval_changed(cond: Condition, bug: dict, ctx: _Context) -> bool:
    field_name = cond.field
    if field_name == "creation_ts":
        operator = "lessthaneq" if cond.operator == "changedbefore" else "greaterthaneq"
        if cond.operator not in ("changedbefore", "changedafter"):
            raise UnsupportedSearch(
                f"Unsupported operator {cond.operator} for creation_ts"
            )
        value = sqlify_date(cond.value, ctx.now).isoformat()
        return _compare_values(
            field_name, operator, bug.get("creation_time"), value, ctx
        )
    if field_name in ("longdesc", "longdescs.count"):
        # The comments are the "history" of longdesc.
        rows = [{"when": c["time"], "who": c["author"]} for c in _public_comments(bug)]
        if cond.operator in ("changedfrom", "changedto"):
            raise UnsupportedSearch(
                f"Invalid operator {cond.operator} for {field_name}"
            )
        return any(_match_change(cond, row, ctx) for row in rows)
    if field_name in COUNT_FIELDS and field_name not in COUNT_HISTORY:
        raise UnsupportedSearch(
            f"Unsupported operator {cond.operator} for {field_name}"
        )
    return any(_match_change(cond, row, ctx) for row in _changes(bug, field_name))


def _eval_condition(cond: Condition, bug: dict, ctx: _Context) -> bool | None:
    if cond.value.strip() == "" and cond.operator not in NO_VALUE_OPERATORS:
        return None
    res = _eval_positive(cond, bug, ctx)
    if res is None:
        return None
    return not res if cond.negate else res


def _multi(field_name, operator, values, cond: Condition, ctx) -> bool | None:
    """Multi-select semantics (`_multiselect_*` in `Search.pm`)."""
    if operator in ("isempty", "isnotempty"):
        return (not values) == (operator == "isempty")
    if operator in (
        "notequals",
        "notregexp",
        "notsubstring",
        "nowords",
        "nowordssubstr",
    ):
        positive = reverse_operator(operator)
        res = _multi(field_name, positive, values, cond, ctx)
        return None if res is None else not res
    if operator in (
        "allwords",
        "allwordssubstr",
        "anyexact",
        "anywords",
        "anywordssubstr",
    ):
        words = (
            _anyexact_values(cond.all_values)
            if operator == "anyexact"
            else _words(cond.value)
        )
        if not words:
            return None
        found = [
            any(_match_value(field_name, operator, v, w, w, ctx) for v in values)
            for w in words
        ]
        return any(found) if operator.startswith("any") else all(found)
    return any(
        _match_value(field_name, operator, v, cond.value, cond.all_values, ctx)
        for v in values
    )


PRODUCT_ALIASES = {"fenix": "Firefox for Android"}


def _product_aliases(cond: Condition) -> Condition:
    if isinstance(cond.all_values, list):
        values = [PRODUCT_ALIASES.get(v.lower(), v) for v in cond.all_values]
        return Condition(
            cond.field, cond.operator, ",".join(values), values, cond.negate
        )
    value = PRODUCT_ALIASES.get(cond.value.lower(), cond.value)
    return Condition(cond.field, cond.operator, value, value, cond.negate)


def _anyexact_values(all_values) -> list[str]:
    if isinstance(all_values, list):
        return all_values
    return _words(all_values)


def _eval_positive(cond: Condition, bug: dict, ctx: _Context) -> bool | None:
    field_name, operator = cond.field, cond.operator

    if operator in CHANGED_OPERATORS:
        return _eval_changed(cond, bug, ctx)

    if field_name == "resolution" and cond.value.strip() == "---":
        if operator in ("equals", "notequals"):
            operator = "isempty" if operator == "equals" else "isnotempty"

    if field_name == "product":
        cond = _product_aliases(cond)

    if field_name in SCALAR_FIELDS or field_name.startswith("cf_"):
        key = SCALAR_FIELDS.get(field_name, field_name)
        actual = bug.get(key)
        if actual is None and field_name.startswith(("cf_status_", "cf_tracking_")):
            actual = "---"
        if field_name == "component" and operator in ("equals", "notequals"):
            match = re.fullmatch(r"(?:(.+?)\s*::\s*)?(.+)", cond.value)
            if match and match.group(1):
                same = _casefold(bug.get("product")) == match.group(1).casefold() and (
                    _casefold(actual) == match.group(2).casefold()
                )
                return same if operator == "equals" else not same
        return _match_value(
            field_name, operator, actual, cond.value, cond.all_values, ctx
        )

    if field_name == "days_elapsed":
        changed = parse_datetime(bug.get("last_change_time")) or EMPTY_DATETIME
        days = (ctx.now.date() - changed.date()).days
        return _match_value(
            field_name, operator, days, cond.value, cond.all_values, ctx
        )

    if field_name in COUNT_FIELDS:
        count = COUNT_FIELDS[field_name](bug)
        return _match_value(
            field_name, operator, count, cond.value, cond.all_values, ctx
        )

    if field_name in USER_FIELDS:
        actual = bug.get(USER_FIELDS[field_name]) or ""
        group = re.fullmatch(r"%group\.([^%]+)%", cond.value.strip())
        if group:
            # `_contact_exact_group`: whether the user is in the group.
            in_group = group.group(1) in ctx.user_groups(actual)
            return not in_group if operator.startswith("not") else in_group
        if re.fullmatch(r"%[\w.]+%", cond.value.strip()):
            raise UnsupportedSearch(
                f"Unsupported pronoun {cond.value} for {field_name}"
            )
        return _match_value(
            field_name, operator, actual, cond.value, cond.all_values, ctx
        )

    if field_name in USER_LIST_FIELDS:
        if re.fullmatch(r"%[\w.]+%", cond.value.strip()):
            raise UnsupportedSearch(
                f"Unsupported pronoun {cond.value} for {field_name}"
            )
        users = [u for u in USER_LIST_FIELDS[field_name](bug) if u]
        # Negative operators are reversed, and check that no user matches.
        if re.match(r"^(no|isempty)", operator):
            positive = reverse_operator(operator)
            return not any(
                _match_value(field_name, positive, u, cond.value, cond.all_values, ctx)
                for u in users
            )
        return any(
            _match_value(field_name, operator, u, cond.value, cond.all_values, ctx)
            for u in users
        )

    if field_name in MULTI_FIELDS:
        values = MULTI_FIELDS[field_name](bug)
        return _multi(field_name, operator, values, cond, ctx)

    if field_name in ATTACHMENT_FIELDS:
        key = ATTACHMENT_FIELDS[field_name]
        attachments = [a for a in bug.get("attachments", []) if not a.get("is_private")]
        if operator in ("isempty", "isnotempty"):
            if key in ("content_type", "file_name", "summary"):
                return operator == "isnotempty"
            raise UnsupportedSearch(f"Invalid operator {operator} for {field_name}")
        values = [a.get(key) for a in attachments]
        return _multi(field_name, operator, values, cond, ctx)

    if field_name == "flagtypes.name":
        flags = [f"{f['name']}{f['status']}" for f in _flags(bug)]
        if operator in ("isempty", "isnotempty"):
            return (not flags) == (operator == "isempty")
        if operator.startswith("not"):
            positive = operator[3:]
            return not any(
                _match_value(field_name, positive, f, cond.value, cond.all_values, ctx)
                for f in flags
            )
        return any(
            _match_value(field_name, operator, f, cond.value, cond.all_values, ctx)
            for f in flags
        )

    if field_name == "longdesc":
        comments = _public_comments(bug)
        if operator in ("isempty", "isnotempty"):
            texts = [c.get("text", "") for c in comments]
            empty = any(t == "" for t in texts)
            return empty if operator == "isempty" else any(t != "" for t in texts)
        if ctx.longdesc_initial:
            comments = [c for c in comments if c.get("count") == 0]
        return any(
            _match_value(
                field_name,
                operator,
                c.get("text", ""),
                cond.value,
                cond.all_values,
                ctx,
            )
            for c in comments
        )

    raise UnsupportedSearch(f"Unsupported field {field_name!r}")


def _eval_group(clause: Clause, bug: dict, ctx: _Context) -> bool | None:
    """`AND_G`: all the conditions must match the same history entry."""
    conditions = [c for c in clause.children if isinstance(c, Condition)]
    if len(conditions) != len(clause.children):
        raise UnsupportedSearch("AND_G groups can only contain conditions")
    if not conditions:
        return None
    fields = {c.field for c in conditions}
    if len(fields) != 1:
        raise UnsupportedSearch("AND_G groups must be about a single field")
    if not all(c.operator in CHANGED_OPERATORS for c in conditions):
        if len(conditions) == 1:
            return _eval_condition(conditions[0], bug, ctx)
        raise UnsupportedSearch(
            "AND_G groups are only supported with changed* operators"
        )
    rows = _changes(bug, conditions[0].field)
    res = any(
        all(_match_change(c, row, ctx) != c.negate for c in conditions) for row in rows
    )
    return not res if clause.negate else res


def _eval(node, bug: dict, ctx: _Context) -> bool | None:
    if isinstance(node, Condition):
        return _eval_condition(node, bug, ctx)
    if node.group:
        return _eval_group(node, bug, ctx)
    results = [
        r for r in (_eval(child, bug, ctx) for child in node.children) if r is not None
    ]
    if not results:
        return None
    res = all(results) if node.joiner == "AND" else any(results)
    return not res if node.negate else res


class Search:
    """A compiled search, to match bugs against.

    Args:
        params: the parameters of the search, as parsed by `parse_qs`.
        now: the current time, for relative dates.
        users: Bugzilla users by email, for their groups.
    """

    def __init__(
        self,
        params: dict[str, list[str]],
        now: datetime.datetime,
        users: dict | None = None,
    ):
        self.params = params
        self.tree = parse(params)
        longdesc_initial = bool(params.get("description")) or bool(
            _first(params, "longdesc_initial")
        )
        self.ctx = _Context(now, users or {}, longdesc_initial)

    def matches(self, bug: dict) -> bool:
        return _eval(self.tree, bug, self.ctx) is not False
