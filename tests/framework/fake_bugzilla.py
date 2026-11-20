# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""An in-memory Bugzilla REST API, served through `responses`.

Mocking at the HTTP level means libmozdata (`Bugzilla`, `BugzillaUser`, ...)
and every rule run unmodified, whatever module they import `Bugzilla` from.

Searches are evaluated on the scenario's bugs by `tests.framework.search`,
which mirrors BMO's semantics and fails on what it doesn't support. Fetching
a bug the scenario doesn't define (by id, or with `bug_id` in a search) is an
error, to make scenarios explicit about which bugs the rule depends on.
"""

import copy
import json
import re
import threading
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

import responses
from libmozdata.bugzilla import Bugzilla, BugzillaUser

from tests.framework.bugs import (
    SIDE_DATA,
    USER_FIELDS,
    USER_LIST_FIELDS,
    make_user,
    missing_field_default,
)
from tests.framework.search import Search, parse_datetime

# Set as the token of `SilentBugzilla`, to tell which changes don't send bugmail.
NOMAIL_TOKEN = "fake-nomail-token"


class UnknownBugError(AssertionError):
    pass


def _split(values: list[str]) -> list[str]:
    return [v for value in values for v in value.split(",") if v]


class FakeBugzilla:
    def __init__(
        self,
        bugs: dict[int, dict],
        users: dict,
        now: str,
        components: dict | None = None,
    ):
        self.bugs = bugs
        self.components = components or {}
        self.users = users
        self.now = now
        self.now_dt = parse_datetime(now)
        self.changes: dict[str, list[dict]] = defaultdict(list)
        self.silent: set[str] = set()
        self.created: list[dict] = []
        self.searches: list[dict] = []
        self.errors: list[str] = []
        self._lock = threading.Lock()

    # Registration

    def register(self, rsps: responses.RequestsMock) -> None:
        api = re.escape(Bugzilla.API_URL)
        user_api = re.escape(BugzillaUser.API_URL)
        base = re.escape(Bugzilla.URL)
        routes = [
            ("GET", rf"{api}/attachment/(\d+)", self._get_attachment_by_id),
            ("GET", rf"{api}/(\d+)/history", self._get_history),
            ("GET", rf"{api}/(\d+)/comment", self._get_comments),
            ("GET", rf"{api}/(\d+)/attachment", self._get_attachments),
            ("GET", rf"{api}/(\d+)", self._get_bug),
            ("GET", rf"{api}", self._get_bugs),
            ("PUT", rf"{api}/(\d+)", self._put_bug),
            ("POST", rf"{api}", self._post_bug),
            ("GET", rf"{user_api}", self._get_users),
            ("GET", rf"{base}/rest/bitly/shorten", self._shorten),
            ("GET", rf"{base}/rest/product", self._get_products),
        ]
        for method, pattern, handler in routes:
            rsps.add_callback(
                method,
                re.compile(pattern + r"/?(\?.*)?$"),
                callback=self._wrap(pattern, handler),
            )

    def _wrap(self, pattern, handler):
        regex = re.compile(pattern)

        def callback(request):
            parsed = urlparse(request.url)
            url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            match = regex.fullmatch(url)
            params = parse_qs(parsed.query, keep_blank_values=True)
            try:
                body = handler(request, params, *match.groups())
            except AssertionError as e:
                # Surfaced by the test, the exception being raised in a thread
                # of libmozdata and possibly swallowed there.
                self.errors.append(str(e))
                body = {"error": True, "message": str(e), "bugs": []}
            return (200, {"Content-Type": "application/json"}, json.dumps(body))

        return callback

    # Helpers

    def _bug(self, bugid) -> dict:
        bug = self.bugs.get(int(bugid))
        if bug is None:
            raise UnknownBugError(
                f"The rule fetched bug {bugid}, which the scenario doesn't define."
                " Add it to the scenario's bugs."
            )
        return bug

    def _ids(self, first, params) -> list[str]:
        return [first] + _split(params.get("ids", []))

    @staticmethod
    def _project(obj: dict, include_fields: list[str]) -> dict:
        fields = set(include_fields) - {"_default", "_all", "_custom", "_extra"}
        if not fields or "_all" in include_fields:
            return {k: v for k, v in obj.items() if k not in SIDE_DATA}
        if "_default" in include_fields:
            res = {k: v for k, v in obj.items() if k not in SIDE_DATA}
        else:
            res = {}
        res["id"] = obj["id"]

        # `attachments.flags` selects a field of the items of a list.
        subfields = defaultdict(set)
        for field in fields:
            if "." in field:
                base, _, sub = field.partition(".")
                subfields[base].add(sub)
        for base, subs in subfields.items():
            fields = (fields - {f"{base}.{s}" for s in subs}) - {base}
            res[base] = [
                {k: v for k, v in item.items() if k in subs}
                for item in obj.get(base, [])
            ]

        if "_custom" in include_fields:
            fields |= {k for k in obj if k.startswith("cf_")}

        # Bugzilla returns the details of the users along with their emails.
        details = {**USER_FIELDS, **USER_LIST_FIELDS}
        fields |= {details[f] for f in fields if f in details and details[f] in obj}

        for field in fields:
            if field in obj:
                res[field] = obj[field]
            elif field in SIDE_DATA:
                res[field] = []
            else:
                default = missing_field_default(field)
                if default is not None:
                    res[field] = default
        return copy.deepcopy(res)

    # Bugs

    def _get_bug(self, request, params, bugid):
        include = _split(params.get("include_fields", []))
        return {"bugs": [self._project(self._bug(bugid), include)], "faults": []}

    def _get_bugs(self, request, params):
        include = _split(params.get("include_fields", []))
        if "id" in params:
            ids = _split(params["id"])
            return {
                "bugs": [self._project(self._bug(i), include) for i in ids],
                "faults": [],
            }

        bug_ids = _split(params.get("bug_id", []))
        for bugid in bug_ids:
            self._bug(bugid)
        search = Search(params, self.now_dt, self.users)
        ids = [i for i in sorted(self.bugs) if search.matches(self.bugs[i])]
        if "count_only" not in params:
            with self._lock:
                self.searches.append({"params": params, "ids": ids})

        if "count_only" in params:
            return {"bug_count": len(ids)}

        offset = int(params.get("offset", ["0"])[0])
        limit = int(params.get("limit", ["0"])[0])
        ids = ids[offset : offset + limit] if limit else ids[offset:]
        return {"bugs": [self._project(self._bug(i), include) for i in ids]}

    def _put_bug(self, request, params, bugid):
        change = json.loads(request.body)
        ids = [str(i) for i in change.pop("ids", [bugid])]
        with self._lock:
            for i in ids:
                self._bug(i)
                self.changes[i].append(copy.deepcopy(change))
                if request.headers.get("X-Bugzilla-API-Key") == NOMAIL_TOKEN:
                    self.silent.add(i)
        return {"bugs": [{"id": int(i), "changes": {}} for i in ids]}

    def _post_bug(self, request, params):
        bug = json.loads(request.body)
        with self._lock:
            self.created.append(bug)
            new_id = 9_000_000 + len(self.created)
        return {"id": new_id}

    # Side data

    def _get_history(self, request, params, first):
        return {
            "bugs": [
                {
                    "id": int(i),
                    "alias": self._bug(i).get("alias"),
                    "history": copy.deepcopy(self._bug(i).get("history", [])),
                }
                for i in self._ids(first, params)
            ]
        }

    def _get_comments(self, request, params, first):
        include = _split(params.get("include_fields", []))
        bugs = {}
        for i in self._ids(first, params):
            comments = self._bug(i).get("comments", [])
            if include:
                comments = [
                    {k: v for k, v in c.items() if k in include} for c in comments
                ]
            bugs[str(i)] = {"comments": copy.deepcopy(comments)}
        return {"bugs": bugs, "comments": {}}

    def _get_attachments(self, request, params, first):
        include = _split(params.get("include_fields", []))
        bugs = {}
        for i in self._ids(first, params):
            attachments = self._bug(i).get("attachments", [])
            if include:
                attachments = [self._project(a, include) for a in attachments]
            bugs[str(i)] = copy.deepcopy(attachments)
        return {"bugs": bugs, "attachments": {}}

    def _get_attachment_by_id(self, request, params, first):
        wanted = {int(first)} | {
            int(i) for i in _split(params.get("attachment_ids", []))
        }
        found = {
            str(a["id"]): copy.deepcopy(a)
            for bug in self.bugs.values()
            for a in bug.get("attachments", [])
            if a["id"] in wanted
        }
        return {"bugs": {}, "attachments": found}

    def _get_products(self, request, params):
        """The products, from the scenario's components and the bugs'."""
        components = {}
        for bug in self.bugs.values():
            key = f"{bug['product']}::{bug['component']}"
            components[key] = {"triage_owner": bug.get("triage_owner", "")}
        for key, component in self.components.items():
            components.setdefault(key, {}).update(component)

        products: dict[str, list] = defaultdict(list)
        for key, component in sorted(components.items()):
            product, _, name = key.partition("::")
            products[product].append(
                {
                    "id": len(products[product]) + 1,
                    "name": name,
                    "default_assigned_to": "nobody@mozilla.org",
                    "triage_owner": "",
                    "team_name": "Mozilla",
                    "is_active": True,
                    **component,
                }
            )

        names = set(_split(params.get("names", [])))
        include = _split(params.get("include_fields", []))
        return {
            "products": [
                self._project({"id": i, "name": name, "components": comps}, include)
                for i, (name, comps) in enumerate(sorted(products.items()))
                if not names or name in names
            ]
        }

    def _shorten(self, request, params):
        return {"url": "https://mzl.la/short"}

    # Users

    def _get_users(self, request, params):
        include = _split(params.get("include_fields", []))
        names = _split(params.get("names", []))
        ids = {int(i) for i in _split(params.get("ids", []))}
        users = [self.get_user(name) for name in names]
        users += [u for u in self.users.values() if u["id"] in ids]
        if include and "_default" not in include and "_all" not in include:
            users = [{k: v for k, v in u.items() if k in include} for u in users]
        return {"users": users, "faults": []}

    def get_user(self, email: str) -> dict:
        user = self.users.get(email) or make_user(email, now=self.now)
        return copy.deepcopy(user)
