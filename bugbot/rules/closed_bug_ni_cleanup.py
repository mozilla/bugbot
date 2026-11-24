# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
from datetime import timedelta
from typing import Any

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla

from bugbot.bzcleaner import Bug
from bugbot.needinfo_cleanup import NeedinfoCleanup

RESOLUTIONS = ["INCOMPLETE", "WORKSFORME", "INVALID", "WONTFIX", "INACTIVE"]
UNMAINTAINED_PRODUCTS = r"Graveyard$|^Invalid Bugs$"


class ClosedBugNiCleanup(NeedinfoCleanup):
    def __init__(self) -> None:
        super().__init__()
        self.delay = timedelta(days=self.get_config("days_closed", 14))
        self.dupe_targets: dict[str, Bug] = {}

    def description(self) -> str:
        return "Clear needinfos on bugs that have been closed or moved to a graveyard product"

    def get_bz_params(self, date: str) -> dict[str, Any]:
        cutoff = lmdutils.get_date_str(lmdutils.get_date_ymd(date) - self.delay)
        return {
            "include_fields": [
                "flags",
                "resolution",
                "cf_last_resolved",
                "product",
                "dupe_of",
                "history",
            ],
            "f1": "flagtypes.name",
            "o1": "substring",
            "v1": "needinfo?",
            "j2": "OR",
            "f2": "OP",
            # Closed as one of RESOLUTIONS more than `delay` ago.
            "f3": "OP",
            "f4": "resolution",
            "o4": "anyexact",
            "v4": ",".join(RESOLUTIONS),
            "f5": "cf_last_resolved",
            "o5": "lessthan",
            "v5": cutoff,
            "f6": "CP",
            # In an unmaintained product, and not moved there in the last `delay`.
            "f7": "OP",
            "f8": "product",
            "o8": "regexp",
            "v8": UNMAINTAINED_PRODUCTS,
            "n9": "1",
            "f9": "product",
            "o9": "changedafter",
            "v9": cutoff,
            "f10": "CP",
            # Duplicates, filtered on the status of their target in `prepare`.
            "f11": "resolution",
            "o11": "equals",
            "v11": "DUPLICATE",
            "f12": "CP",
        }

    def get_dupe_targets(self, bugids: set[int]) -> dict[str, Bug]:
        def handler(bug: Bug, data: dict[str, Bug]) -> None:
            data[str(bug["id"])] = bug

        targets: dict[str, Bug] = {}
        Bugzilla(
            sorted(bugids),
            include_fields=["id", "resolution", "cf_last_resolved"],
            bughandler=handler,
            bugdata=targets,
        ).wait()
        return targets

    def prepare(self, bugs: dict[str, Bug]) -> None:
        bugids = {
            bug["dupe_of"]
            for bug in bugs.values()
            if bug["resolution"] == "DUPLICATE" and bug.get("dupe_of")
        }
        self.dupe_targets = self.get_dupe_targets(bugids) if bugids else {}

    def get_reason(self, bug: Bug) -> tuple[str, str] | None:
        if bug["resolution"] in RESOLUTIONS and self.is_closed_before(bug, self.delay):
            resolved_at = bug["cf_last_resolved"]
            return (
                f"this bug has been closed as {bug['resolution']} for {self.time_since(resolved_at)}",
                resolved_at,
            )

        if re.search(UNMAINTAINED_PRODUCTS, bug["product"]):
            moved_at = next(
                (
                    entry["when"]
                    for entry in reversed(bug.get("history", []))
                    if any(
                        change["field_name"] == "product"
                        and change["added"] == bug["product"]
                        for change in entry["changes"]
                    )
                ),
                None,
            )
            if moved_at and self.is_older_than(moved_at, self.delay):
                return (
                    f"this bug has been moved to the {bug['product']} product",
                    moved_at,
                )

        if bug["resolution"] == "DUPLICATE":
            duplicated_at = bug.get("cf_last_resolved")
            target = self.dupe_targets.get(str(bug.get("dupe_of")))
            if duplicated_at and target and self.is_closed_before(target, self.delay):
                return (
                    f"this bug is a duplicate of bug {target['id']}, which has been closed for {self.time_since(target['cf_last_resolved'])}",
                    duplicated_at,
                )

        return None

    def get_needinfos_to_clear(
        self, bug: Bug
    ) -> tuple[list[dict[str, Any]], str | None]:
        eligibility = self.get_reason(bug)
        if eligibility is None:
            return [], None

        reason, changed_at = eligibility
        cutoff = lmdutils.get_date_ymd(changed_at)
        needinfos = [
            flag
            for flag in self.get_pending_needinfos(bug)
            if lmdutils.get_date_ymd(flag["modification_date"]) <= cutoff
        ]
        return needinfos, f"Clearing the needinfo request since {reason}."


if __name__ == "__main__":
    ClosedBugNiCleanup().run()
