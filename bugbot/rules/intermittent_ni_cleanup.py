# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import timedelta
from typing import Any

from libmozdata import utils as lmdutils

from bugbot.bzcleaner import Bug, BzCleaner

CLOSED_STATUSES = {"RESOLVED", "VERIFIED", "CLOSED"}
FAILURE_KEYWORDS = ["intermittent-failure", "perma-failure"]


class IntermittentNiCleanup(BzCleaner):
    def __init__(self) -> None:
        super().__init__()
        self.days_since_resolved = self.get_config("days_since_resolved", 7)

    def description(self) -> str:
        return "Clear needinfos on resolved intermittent/perma failure bugs"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

    def get_bz_params(self, date: str) -> dict[str, Any]:
        resolved_before = lmdutils.get_date_str(
            lmdutils.get_date_ymd(date) - timedelta(days=self.days_since_resolved)
        )
        return {
            "include_fields": ["flags", "status", "keywords", "cf_last_resolved"],
            "status": sorted(CLOSED_STATUSES),
            "keywords_type": "anywords",
            "keywords": ",".join(FAILURE_KEYWORDS),
            "f1": "flagtypes.name",
            "o1": "substring",
            "v1": "needinfo?",
            # Give people some time to reopen the bug before clearing the needinfos.
            "f2": "cf_last_resolved",
            "o2": "lessthan",
            "v2": resolved_before,
        }

    def handle_bug(self, bug: Bug, data: dict[str, Any]) -> Bug:
        data[str(bug["id"])] = {
            "flags": bug["flags"],
            "status": bug["status"],
            "keywords": bug["keywords"],
            "cf_last_resolved": bug["cf_last_resolved"],
        }
        return bug

    @staticmethod
    def get_stale_needinfos(bug: Bug) -> list[dict[str, Any]]:
        last_resolved = bug.get("cf_last_resolved")
        if not last_resolved:
            return []
        last_resolved = lmdutils.get_date_ymd(last_resolved)

        # Needinfos requested after the bug was resolved were likely
        # intentional, so we leave them alone.
        return [
            flag
            for flag in bug.get("flags", [])
            if flag["name"] == "needinfo"
            and flag["status"] == "?"
            and lmdutils.get_date_ymd(flag["creation_date"]) < last_resolved
        ]

    def get_bugs(
        self,
        date: str = "today",
        bug_ids: list[int] = [],
        chunk_size: int | None = None,
    ) -> dict[str, Any]:
        bugs = super().get_bugs(date=date, bug_ids=bug_ids, chunk_size=chunk_size)
        self.autofix_changes = {}
        comment = (
            "Clearing the needinfo request since this test failure bug has been "
            f"resolved.\n\n{self.get_documentation()}"
        )
        for bugid in sorted(bugs, key=int):
            bug = bugs[bugid]
            if bug["status"] not in CLOSED_STATUSES:
                continue
            if not set(bug.get("keywords", [])) & set(FAILURE_KEYWORDS):
                continue
            needinfos = self.get_stale_needinfos(bug)
            if not needinfos:
                continue
            self.autofix_changes[bugid] = {
                "flags": [{"id": flag["id"], "status": "X"} for flag in needinfos],
                "comment": {"body": comment},
            }
            if len(self.autofix_changes) >= self.normal_changes_max:
                break
        return {bugid: bugs[bugid] for bugid in self.autofix_changes}

    def get_email_data(self, date: str) -> list[Any]:
        # Run the autofix pipeline without sending a summary email.
        super().get_email_data(date)
        return []


if __name__ == "__main__":
    IntermittentNiCleanup().run()
