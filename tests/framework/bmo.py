# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Run scenarios against a local BMO, in Docker (see tests/bmo/).

- `ensure_running` starts the containers if needed.
- `Database` loads the bugs of a scenario into BMO's database. The REST API
  can't create bugs in the past, with their history, so they're written
  directly in BMO's tables. It also moves the clocks of BMO and MySQL to the
  time of the scenario (libfaketime).
- `LocalBugzilla` forwards the requests the rule makes to bugzilla.mozilla.org
  to the local BMO, recording the changes and the searches.
"""

import datetime
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
from collections import defaultdict
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlparse

import pymysql  # type: ignore[import-untyped]
import requests
import responses

from tests.framework.bugs import make_user, parse_datetime

# It logs every request passed through to the local BMO.
logging.getLogger("responses").setLevel(logging.WARNING)

COMPOSE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "bmo",
    "docker-compose.yml",
)
STATE_DIR = os.environ.get("BUGBOT_BMO_STATE", "/tmp/bugbot-bmo")
HTTP_PORT = int(os.environ.get("BUGBOT_BMO_PORT", "18000"))
DB_PORT = int(os.environ.get("BUGBOT_BMO_DB_PORT", "13306"))
MEMCACHED_PORT = int(os.environ.get("BUGBOT_BMO_MEMCACHED_PORT", "21211"))
URL = f"http://localhost:{HTTP_PORT}"
# As seen from the bmo container.
PRODUCT_DETAILS = "http://productdetails:8080/product_details"

ADMIN = "admin@mozilla.bugs"
# Set as the token of `SilentBugzilla`, to tell which changes don't send bugmail.
NOMAIL_TOKEN = "fake-nomail-token"

# The tables with the data of the bugs, emptied before each scenario.
BUG_TABLES = [
    "bug_group_map",
    "bugs_activity",
    "cc",
    "dependencies",
    "regressions",
    "duplicates",
    "flags",
    "keywords",
    "attach_data",
    "attachments",
    "bug_see_also",
    "bug_mentors",
    "tracking_flags_bugs",
    "longdescs",
    "bugs_fulltext",
    "bugs",
]

# Production custom fields which don't exist in BMO's dev data.
CUSTOM_FIELDS = {
    "cf_a11y_review_project_flag": "single_select",
    "cf_accessibility_severity": "single_select",
    "cf_cab_review": "single_select",
    "cf_fx_iteration": "single_select",
    "cf_fx_points": "single_select",
    "cf_has_str": "single_select",
    "cf_performance_impact": "single_select",
    "cf_qa_whiteboard": "freetext",
    "cf_webcompat_priority": "single_select",
    "cf_webcompat_score": "single_select",
}

TRACKING_VALUES = [
    "---",
    "?",
    "+",
    "-",
    "affected",
    "unaffected",
    "fixed",
    "verified",
    "wontfix",
    "fix-optional",
    "disabled",
    "verified disabled",
]

# The names of the fields in the history returned by the REST API, which
# aren't the names of the fields in the database.
HISTORY_FIELDS = {
    "blocks": "blocked",
    "creator": "reporter",
    "depends_on": "dependson",
    "dupe_of": "dup_id",
    "groups": "bug_group",
    "platform": "rep_platform",
    "regressions": "regresses",
    "severity": "bug_severity",
    "status": "bug_status",
    "summary": "short_desc",
    "type": "bug_type",
    "url": "bug_file_loc",
    "whiteboard": "status_whiteboard",
}

# Parameters of a search which don't select bugs.
NON_CRITERIA = {
    "include_fields",
    "exclude_fields",
    "limit",
    "offset",
    "order",
    "count_only",
    "api_key",
    "Bugzilla_api_key",
}


class BMOUnavailable(Exception):
    pass


def search_criteria(params: dict[str, list[str]]) -> dict[str, list[str]]:
    """The parameters of a search which select the bugs, in order."""

    def key(name):
        # Custom search parameters in order: f1, o1, v1, f2...
        match = re.fullmatch(r"([fovnj])(\d+)", name)
        if match:
            return (1, int(match.group(2)), "fovnj".index(match.group(1)))
        return (0, name, 0)

    return {k: params[k] for k in sorted(params, key=key) if k not in NON_CRITERIA}


# The containers


def _compose(*args, check=True, capture=False):
    env = {**os.environ, "BUGBOT_BMO_STATE": STATE_DIR}
    return subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, *args],
        env=env,
        check=check,
        capture_output=capture,
        text=True,
    )


def is_running() -> bool:
    try:
        return requests.get(f"{URL}/rest/version", timeout=2).ok
    except requests.RequestException:
        return False


def _prepare_state_dir():
    # Created before the containers, so that it isn't created by Docker as root.
    os.makedirs(f"{STATE_DIR}/product_details", exist_ok=True)
    faketime = f"{STATE_DIR}/faketime"
    if not os.path.exists(faketime):
        with open(faketime, "w") as f:
            f.write("+0\n")


_database = None
_lock = threading.Lock()


def ensure_running(timeout: int = 900) -> "Database":
    """Start the local BMO if it isn't running, and return its database.

    Raises:
        BMOUnavailable: if Docker isn't available, or BMO doesn't start.
    """
    global _database
    with _lock:
        if _database is not None:
            return _database

        if not is_running():
            if not shutil.which("docker"):
                raise BMOUnavailable("Docker is required to run the scenarios")
            _prepare_state_dir()
            # Building the images the first time takes a few minutes, and
            # starting BMO about a minute.
            _compose("up", "--detach", "--build")
            start = time.monotonic()
            while not is_running():
                status = _compose(
                    "ps", "--all", "--format", "{{.Service}} {{.State}}", capture=True
                ).stdout
                if time.monotonic() - start > timeout or "exited" in status:
                    logs = _compose("logs", "--tail", "20", capture=True, check=False)
                    raise BMOUnavailable(
                        f"BMO didn't start:\n{status}\n{logs.stdout}{logs.stderr}"
                    )
                time.sleep(2)

        _prepare_state_dir()
        database = Database()
        database.setup()
        _database = database
        return database


def stop():
    _compose("down")


# The database


def _sql_time(value) -> str | None:
    dt = parse_datetime(value)
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


class Database:
    def __init__(self):
        self.db = pymysql.connect(
            host="127.0.0.1",
            port=DB_PORT,
            user="bugs",
            password="bugs",
            database="bugs",
            autocommit=True,
        )
        self._users: dict[str, int] = {}
        self._bug_columns: set[str] = set()
        self.api_key = ""

    def q(self, sql, *args):
        with self.db.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.fetchall()

    def one(self, sql, *args):
        rows = self.q(sql, *args)
        return rows[0][0] if rows else None

    def insert(self, table, **values) -> int:
        columns = ", ".join(f"`{column}`" for column in values)
        placeholders = ", ".join(["%s"] * len(values))
        with self.db.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})",
                list(values.values()),
            )
            return cursor.lastrowid

    def flush_caches(self):
        """BMO caches fields, products... in memcached."""
        with socket.create_connection(("127.0.0.1", MEMCACHED_PORT)) as s:
            s.sendall(b"flush_all\r\n")
            s.recv(100)

    # Setup, once

    def setup(self):
        """Make BMO's dev data closer to production."""
        for name, field_type in CUSTOM_FIELDS.items():
            if not self.field_id(name):
                _compose(
                    "exec",
                    "-T",
                    "bmo",
                    "perl",
                    "scripts/addcustomfield.pl",
                    name,
                    field_type,
                    capture=True,
                )
        # addcustomfield.pl creates obsolete fields.
        for name in CUSTOM_FIELDS:
            self.q(
                "UPDATE fielddefs SET obsolete=0, description=%s WHERE name=%s",
                name[3:].replace("_", "-"),
                name,
            )

        # Free text fields in BMO's dev data, only search aliases in production.
        self.q(
            "UPDATE fielddefs SET obsolete=1 WHERE type=1 AND name REGEXP"
            " '^cf_(status|tracking)_(firefox|thunderbird)_(nightly|beta|release|esr)$'"
        )

        platform = self.one("SELECT id FROM rep_platform WHERE value='Unspecified'")
        op_sys = self.one("SELECT id FROM op_sys WHERE value='Unspecified'")
        self.q(
            "UPDATE products SET default_platform_id=%s WHERE default_platform_id IS NULL"
            " OR default_platform_id NOT IN (SELECT id FROM rep_platform)",
            platform,
        )
        self.q(
            "UPDATE products SET default_op_sys_id=%s WHERE default_op_sys_id IS NULL"
            " OR default_op_sys_id NOT IN (SELECT id FROM op_sys)",
            op_sys,
        )
        self.q(
            "UPDATE tracking_flags_values SET setter_group_id="
            "(SELECT id FROM `groups` WHERE name='editbugs') WHERE setter_group_id IS NULL"
        )
        self.q(
            "UPDATE params SET value=%s WHERE name='product_details_endpoint'",
            PRODUCT_DETAILS,
        )

        self._bug_columns = {row[0] for row in self.q("SHOW COLUMNS FROM bugs")}
        self.api_key = self._api_key()
        self.flush_caches()

    def _api_key(self) -> str:
        user_id = self.user(ADMIN)
        key = self.one(
            "SELECT api_key FROM user_api_keys WHERE user_id=%s AND revoked=0", user_id
        )
        if not key:
            key = secrets.token_hex(20)
            self.insert(
                "user_api_keys", user_id=user_id, api_key=key, description="scenarios"
            )
        return key

    # Time and versions

    def set_time(self, now: str, tolerance: int = 5, timeout: float = 10):
        """Move the clocks of BMO and MySQL to `now`.

        libfaketime rereads the offset at most every second, so wait until
        MySQL and BMO (the Date header of its responses) both use it.
        """
        target = parse_datetime(now)
        assert target is not None
        target = target.replace(tzinfo=datetime.timezone.utc)
        offset = target - datetime.datetime.now(datetime.timezone.utc)
        with open(f"{STATE_DIR}/faketime", "w") as f:
            f.write(f"{int(offset.total_seconds()):+d}\n")

        def close(dt):
            return abs((dt - target).total_seconds()) < tolerance

        start = time.monotonic()
        while True:
            mysql_now = self.one("SELECT UTC_TIMESTAMP()").replace(
                tzinfo=datetime.timezone.utc
            )
            date = requests.head(f"{URL}/rest/version", timeout=5).headers["Date"]
            bmo_now = parsedate_to_datetime(date)
            if close(mysql_now) and close(bmo_now):
                return
            if time.monotonic() - start > timeout:
                raise BMOUnavailable(
                    f"The clocks didn't move to {now}: MySQL is at {mysql_now}, "
                    f"BMO at {bmo_now}"
                )
            time.sleep(0.05)

    def set_versions(self, versions: dict | None):
        """The Firefox versions BMO gets from product-details, for the
        `cf_status_firefox_release`... aliases in searches."""
        versions = versions or {}
        data = {
            "FIREFOX_NIGHTLY": f"{versions.get('nightly', 0)}.0a1",
            "LATEST_FIREFOX_DEVEL_VERSION": f"{versions.get('beta', 0)}.0b1",
            "LATEST_FIREFOX_VERSION": f"{versions.get('release', 0)}.0",
            "FIREFOX_ESR": f"{versions.get('esr', 0)}.0esr",
        }
        with open(f"{STATE_DIR}/product_details/firefox_versions.json", "w") as f:
            json.dump(data, f)

    # Entities

    def user(self, email: str, data: dict | None = None) -> int:
        user_id = self._users.get(email) or self.one(
            "SELECT userid FROM profiles WHERE login_name=%s", email
        )
        if not user_id:
            nick = (data or {}).get("nick") or email.split("@")[0]
            # Nicknames are unique in BMO.
            if self.one("SELECT userid FROM profiles WHERE nickname=%s", nick):
                nick = email
            user_id = self.insert(
                "profiles",
                login_name=email,
                cryptpassword="*",
                realname=(data or {}).get("real_name", nick),
                nickname=nick,
                disabledtext="",
                is_enabled=1,
            )
        if data is not None:
            self.q(
                "UPDATE profiles SET realname=%s, is_enabled=%s, disabledtext=%s,"
                " last_seen_date=%s, last_activity_ts=%s, creation_ts=%s"
                " WHERE userid=%s",
                data.get("real_name", ""),
                1 if data.get("can_login", True) else 0,
                "" if data.get("can_login", True) else "Disabled",
                _sql_time(data.get("last_seen_date")),
                _sql_time(data.get("last_activity_time")),
                _sql_time(data.get("creation_time")),
                user_id,
            )
            # The groups of the user, e.g. for %group.editbugs% in searches.
            self.q(
                "DELETE FROM user_group_map WHERE user_id=%s AND isbless=0"
                " AND grant_type=0",
                user_id,
            )
            for group in data.get("groups", []):
                name = group["name"] if isinstance(group, dict) else group
                group_id = self.one("SELECT id FROM `groups` WHERE name=%s", name)
                if group_id:
                    self.insert(
                        "user_group_map",
                        user_id=user_id,
                        group_id=group_id,
                        isbless=0,
                        grant_type=0,
                    )
        self._users[email] = user_id
        return user_id

    def product(self, name: str) -> int:
        product_id = self.one("SELECT id FROM products WHERE name=%s", name)
        if not product_id:
            classification = self.one(
                "SELECT id FROM classifications WHERE name='Components'"
            )
            product_id = self.insert(
                "products",
                name=name,
                classification_id=classification or 1,
                description=name,
                defaultmilestone="---",
                default_version="unspecified",
                default_platform_id=self.one(
                    "SELECT id FROM rep_platform WHERE value='Unspecified'"
                ),
                default_op_sys_id=self.one(
                    "SELECT id FROM op_sys WHERE value='Unspecified'"
                ),
            )
            self.insert("versions", value="unspecified", product_id=product_id)
            self.insert("milestones", value="---", product_id=product_id, sortkey=0)
        return product_id

    def component(self, product: str, name: str, info: dict | None = None) -> int:
        info = info or {}
        product_id = self.product(product)
        component_id = self.one(
            "SELECT id FROM components WHERE name=%s AND product_id=%s",
            name,
            product_id,
        )
        assignee = self.user(info.get("default_assigned_to") or "nobody@mozilla.org")
        if not component_id:
            component_id = self.insert(
                "components",
                name=name,
                product_id=product_id,
                initialowner=assignee,
                description=name,
            )
        owner = info.get("triage_owner")
        self.q(
            "UPDATE components SET initialowner=%s, triage_owner_id=%s, team_name=%s"
            " WHERE id=%s",
            assignee,
            self.user(owner) if owner else None,
            info.get("team_name", "Mozilla"),
            component_id,
        )
        return component_id

    def value(self, table: str, product_id: int, value: str):
        if not self.one(
            f"SELECT id FROM {table} WHERE value=%s AND product_id=%s",
            value,
            product_id,
        ):
            extra = {"sortkey": 0} if table == "milestones" else {}
            self.insert(table, value=value, product_id=product_id, **extra)

    def custom_value(self, field: str, value: str):
        """Make sure that a value of a custom select field exists."""
        if not self.one(f"SELECT id FROM `{field}` WHERE value=%s", value):
            self.insert(field, value=value, sortkey=0, isactive=1)

    def keyword(self, name: str) -> int:
        keyword_id = self.one("SELECT id FROM keyworddefs WHERE name=%s", name)
        if not keyword_id:
            keyword_id = self.insert("keyworddefs", name=name, description=name)
        return keyword_id

    def field_id(self, name: str) -> int | None:
        return self.one("SELECT id FROM fielddefs WHERE name=%s", name)

    def tracking_flag(self, name: str, product_id: int) -> int:
        flag_id = self.one("SELECT id FROM tracking_flags WHERE name=%s", name)
        if not flag_id:
            description = name[3:].replace("_", "-")
            sortkey = self.one("SELECT MAX(sortkey) FROM fielddefs") or 0
            field_id = self.insert(
                "fielddefs",
                name=name,
                type=99,
                custom=1,
                description=description,
                mailhead=0,
                sortkey=sortkey + 1,
                obsolete=0,
                enter_bug=0,
                buglist=1,
                is_mandatory=0,
                is_numeric=0,
            )
            flag_id = self.insert(
                "tracking_flags",
                field_id=field_id,
                name=name,
                description=description,
                type="tracking",
                sortkey=0,
                enter_bug=1,
                is_active=1,
            )
            editbugs = self.one("SELECT id FROM `groups` WHERE name='editbugs'")
            for i, value in enumerate(TRACKING_VALUES):
                self.insert(
                    "tracking_flags_values",
                    tracking_flag_id=flag_id,
                    value=value,
                    sortkey=i,
                    enter_bug=1,
                    is_active=1,
                    setter_group_id=editbugs,
                )
        if not self.one(
            "SELECT id FROM tracking_flags_visibility"
            " WHERE tracking_flag_id=%s AND product_id=%s",
            flag_id,
            product_id,
        ):
            self.insert(
                "tracking_flags_visibility",
                tracking_flag_id=flag_id,
                product_id=product_id,
            )
        return flag_id

    def flag_type(self, name: str) -> int:
        type_id = self.one("SELECT id FROM flagtypes WHERE name=%s", name)
        if not type_id:
            type_id = self.insert(
                "flagtypes",
                name=name,
                description=name,
                target_type="b",
                is_active=1,
                is_requestable=1,
                is_requesteeble=1,
                is_multiplicable=1,
                sortkey=0,
            )
            self.insert(
                "flaginclusions", type_id=type_id, product_id=None, component_id=None
            )
        return type_id

    # Bugs

    def load(
        self,
        bugs: dict[int, dict],
        users: dict[str, dict],
        now: str,
        components: dict | None = None,
        versions: dict | None = None,
    ):
        """Replace the bugs of the database with the given (normalized) bugs."""
        self.set_time(now)
        self.set_versions(versions)

        self.q("SET FOREIGN_KEY_CHECKS=0")
        for table in BUG_TABLES:
            self.q(f"DELETE FROM `{table}`")
        self.q("SET FOREIGN_KEY_CHECKS=1")

        # All the users the bugs mention, with their defaults (active users).
        for email in sorted(_emails(bugs) | set(users)):
            self.user(email, users.get(email) or make_user(email, now=now))
        for key, info in (components or {}).items():
            product, _, name = key.partition("::")
            self.component(product, name, info)

        # The tracking flags of the bugs exist in all the products, as the
        # flags of the current versions do on production.
        products = {self.product(bug["product"]) for bug in bugs.values()}
        flags = {
            name
            for bug in bugs.values()
            for name in bug
            if name.startswith(("cf_status_", "cf_tracking_"))
            and not re.search(r"_(nightly|beta|release|esr|relnote)$", name)
        }
        for name in sorted(flags):
            for product_id in products:
                self.tracking_flag(name, product_id)

        self.q("SET FOREIGN_KEY_CHECKS=0")
        try:
            for bug in bugs.values():
                self._insert_bug(bug, components or {})
            for bug in bugs.values():
                self._insert_relations(bug)
        finally:
            self.q("SET FOREIGN_KEY_CHECKS=1")
        self.flush_caches()

    def _insert_bug(self, bug: dict, components: dict):
        product_id = self.product(bug["product"])
        key = f"{bug['product']}::{bug['component']}"
        info = {"triage_owner": bug.get("triage_owner"), **components.get(key, {})}
        component_id = self.component(bug["product"], bug["component"], info)
        self.value("versions", product_id, bug["version"])
        self.value("milestones", product_id, bug["target_milestone"])
        user = self.user

        columns = {
            "bug_id": bug["id"],
            "assigned_to": user(bug["assigned_to"]),
            "bug_file_loc": bug["url"] or "",
            "bug_severity": bug["severity"],
            "bug_status": bug["status"],
            "bug_type": bug["type"],
            "creation_ts": _sql_time(bug["creation_time"]),
            "delta_ts": _sql_time(bug["last_change_time"]),
            "short_desc": bug["summary"],
            "op_sys": bug["op_sys"],
            "priority": bug["priority"],
            "product_id": product_id,
            "rep_platform": bug["platform"],
            "reporter": user(bug["creator"]),
            "version": bug["version"],
            "component_id": component_id,
            "resolution": bug["resolution"],
            "target_milestone": bug["target_milestone"],
            "qa_contact": user(bug["qa_contact"]) if bug.get("qa_contact") else None,
            "status_whiteboard": bug["whiteboard"],
            "everconfirmed": 1 if bug["is_confirmed"] else 0,
            "reporter_accessible": 1 if bug["is_creator_accessible"] else 0,
            "cclist_accessible": 1 if bug["is_cc_accessible"] else 0,
            "estimated_time": bug.get("estimated_time", 0),
            "remaining_time": bug.get("remaining_time", 0),
            "deadline": _sql_time(bug.get("deadline")),
            "alias": bug.get("alias"),
            "votes": bug.get("votes", 0),
        }
        # Custom fields stored in the bugs table (the tracking flags aren't).
        for name, value in bug.items():
            # Unset fields get the defaults of the table.
            if (
                name.startswith("cf_")
                and name in self._bug_columns
                and value is not None
            ):
                field_type = self.one("SELECT type FROM fielddefs WHERE name=%s", name)
                if field_type == 5:  # datetime
                    value = _sql_time(value)
                elif field_type == 2:  # single select
                    self.custom_value(name, value)
                columns[name] = value
        self.insert("bugs", **columns)

        comments = bug.get("comments", [])
        self.insert(
            "bugs_fulltext",
            bug_id=bug["id"],
            short_desc=bug["summary"],
            comments=" ".join(c["text"] for c in comments),
            comments_noprivate=" ".join(
                c["text"] for c in comments if not c["is_private"]
            ),
        )

        for name, value in bug.items():
            if (
                name.startswith(("cf_status_", "cf_tracking_"))
                and name not in self._bug_columns
                and value not in (None, "---")
            ):
                flag_id = self.tracking_flag(name, product_id)
                self.insert(
                    "tracking_flags_bugs",
                    tracking_flag_id=flag_id,
                    bug_id=bug["id"],
                    value=value,
                )

        for keyword in bug["keywords"]:
            self.insert("keywords", bug_id=bug["id"], keywordid=self.keyword(keyword))
        for email in bug["cc"]:
            self.insert("cc", bug_id=bug["id"], who=user(email))
        for email in bug.get("mentors", []):
            self.insert("bug_mentors", bug_id=bug["id"], user_id=user(email))
        for url in bug["see_also"]:
            self.insert(
                "bug_see_also",
                bug_id=bug["id"],
                value=url,
                **{"class": "Bugzilla::BugUrl::General"},
            )
        for group in bug["groups"]:
            name = group["name"] if isinstance(group, dict) else group
            group_id = self.one("SELECT id FROM `groups` WHERE name=%s", name)
            assert group_id, f"Unknown group {name} (bug {bug['id']})"
            self.insert("bug_group_map", bug_id=bug["id"], group_id=group_id)

        for comment in comments:
            self.insert(
                "longdescs",
                comment_id=comment["id"],
                bug_id=bug["id"],
                who=user(comment["author"]),
                bug_when=_sql_time(comment["time"]),
                thetext=comment["text"],
                isprivate=1 if comment["is_private"] else 0,
                already_wrapped=0,
                type=0,
                work_time=0,
                is_markdown=1,
                edit_count=0,
            )

        attachments = bug.get("attachments", [])
        for attachment in attachments:
            self.insert(
                "attachments",
                attach_id=attachment["id"],
                bug_id=bug["id"],
                creation_ts=_sql_time(attachment["creation_time"]),
                modification_time=_sql_time(attachment["last_change_time"]),
                description=attachment["summary"],
                mimetype=attachment["content_type"],
                ispatch=attachment["is_patch"],
                filename=attachment["file_name"],
                submitter_id=user(attachment["creator"]),
                isobsolete=attachment["is_obsolete"],
                isprivate=attachment["is_private"],
                attach_size=0,
            )

        flags = [(flag, None) for flag in bug["flags"]]
        flags += [(flag, a["id"]) for a in attachments for flag in a.get("flags", [])]
        for flag, attach_id in flags:
            self.insert(
                "flags",
                id=flag["id"],
                type_id=self.flag_type(flag["name"]),
                status=flag["status"],
                bug_id=bug["id"],
                attach_id=attach_id,
                creation_date=_sql_time(flag["creation_date"]),
                modification_date=_sql_time(flag["modification_date"]),
                setter_id=user(flag["setter"]),
                requestee_id=user(flag["requestee"]) if flag.get("requestee") else None,
            )

        for entry in bug.get("history", []):
            for change in entry["changes"]:
                name = HISTORY_FIELDS.get(change["field_name"], change["field_name"])
                field_id = self.field_id(name)
                if field_id is None and name.startswith(("cf_status_", "cf_tracking_")):
                    self.tracking_flag(name, product_id)
                    field_id = self.field_id(name)
                assert field_id, (
                    f"Unknown field {change['field_name']!r} in the history of bug "
                    f"{bug['id']}"
                )
                self.insert(
                    "bugs_activity",
                    bug_id=bug["id"],
                    who=user(entry["who"]),
                    bug_when=_sql_time(entry["when"]),
                    fieldid=field_id,
                    added=change["added"],
                    removed=change["removed"],
                    attach_id=change.get("attachment_id"),
                )

    def _insert_relations(self, bug: dict):
        for other in bug["depends_on"]:
            self.insert("dependencies", blocked=bug["id"], dependson=other)
        for other in bug["regressed_by"]:
            self.insert("regressions", regresses=bug["id"], regressed_by=other)
        if bug.get("dupe_of"):
            self.insert("duplicates", dupe=bug["id"], dupe_of=bug["dupe_of"])


def _emails(bugs: dict[int, dict]) -> set[str]:
    """All the users mentioned by the bugs."""
    emails = set()
    for bug in bugs.values():
        for field in ("assigned_to", "creator", "qa_contact", "triage_owner"):
            if bug.get(field):
                emails.add(bug[field])
        emails |= set(bug["cc"]) | set(bug.get("mentors", []))
        for flag in bug["flags"]:
            emails |= {flag.get("setter"), flag.get("requestee")}
        for comment in bug.get("comments", []):
            emails.add(comment["author"])
        for attachment in bug.get("attachments", []):
            emails.add(attachment["creator"])
            for flag in attachment.get("flags", []):
                emails |= {flag.get("setter"), flag.get("requestee")}
        for entry in bug.get("history", []):
            emails.add(entry["who"])
    return {email for email in emails if email}


# Forwarding the requests of the rule


class LocalBugzilla:
    """Serve bugzilla.mozilla.org with the local BMO, for a scenario."""

    def __init__(
        self,
        bugs: dict[int, dict],
        users: dict[str, dict],
        now: str,
        components: dict | None = None,
        versions: dict | None = None,
    ):
        self.database = ensure_running()
        self.database.load(bugs, users, now, components, versions)
        self.bug_ids = set(bugs)
        self.changes: dict[str, list[dict]] = defaultdict(list)
        self.silent: set[str] = set()
        self.created: list[dict] = []
        self.searches: list[dict] = []
        self.errors: list[str] = []
        self._session = requests.Session()
        self._lock = threading.Lock()

    def register(self, rsps: responses.RequestsMock) -> None:
        rsps.add_passthru(URL)
        for method in ("GET", "PUT", "POST"):
            rsps.add_callback(
                method,
                re.compile(r"https://bugzilla\.mozilla\.org/.*"),
                callback=self._forward,
            )

    def _forward(self, request):
        url = urlparse(request.url)
        path = url.path.rstrip("/")
        params = parse_qs(url.query, keep_blank_values=True)

        if path == "/rest/bitly/shorten":
            return (200, {}, json.dumps({"url": "https://mzl.la/short"}))

        response = self._session.request(
            request.method,
            URL + url.path + ("?" + url.query if url.query else ""),
            data=request.body,
            headers={
                "X-Bugzilla-API-Key": self.database.api_key,
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        try:
            body = response.json()
        except ValueError:
            body = {}

        with self._lock:
            if body.get("error"):
                self.errors.append(
                    f"BMO rejected {request.method} {url.path}?{url.query}: "
                    f"{body.get('message')}"
                )
            if request.method == "PUT":
                change = json.loads(request.body)
                silent = request.headers.get("X-Bugzilla-API-Key") == NOMAIL_TOKEN
                for bugid in change.pop("ids", [path.rsplit("/", 1)[-1]]):
                    self.changes[str(bugid)].append(change)
                    if silent:
                        self.silent.add(str(bugid))
            elif request.method == "POST":
                self.created.append(json.loads(request.body))
            elif (
                path == "/rest/bug"
                and "id" not in params
                and "count_only" not in params
            ):
                self.searches.append(
                    {
                        "params": params,
                        "ids": [bug["id"] for bug in body.get("bugs", [])],
                    }
                )
            for fault in body.get("faults", []):
                self.errors.append(f"BMO couldn't find {fault}")
            for key in ("id", "bug_id"):
                if path != "/rest/bug" or key not in params:
                    continue
                wanted = {int(i) for v in params[key] for i in v.split(",") if i}
                missing = sorted(wanted - self.bug_ids)
                if missing:
                    self.errors.append(
                        f"The rule fetched bugs {missing}, which the scenario "
                        "doesn't define. Add them to the scenario's bugs."
                    )

        return (
            response.status_code,
            {"Content-Type": response.headers.get("Content-Type", "application/json")},
            response.content,
        )

    def search(self, criteria: dict[str, list[str]]) -> set[int]:
        """The bugs matching a search, on the local BMO."""
        response = self._session.get(
            f"{URL}/rest/bug",
            params={**criteria, "include_fields": ["id"]},
            headers={"X-Bugzilla-API-Key": self.database.api_key},
            timeout=120,
        )
        data = response.json()
        if data.get("error"):
            raise AssertionError(f"BMO rejected the search: {data.get('message')}")
        return {int(bug["id"]) for bug in data["bugs"]}
