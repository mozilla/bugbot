# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import timedelta
from typing import Any

from libmozdata import utils as lmdutils

from bugbot.bzcleaner import Bug
from bugbot.needinfo_cleanup import CLOSED_STATUSES, NeedinfoCleanup

FAILURE_KEYWORDS = ["intermittent-failure", "perma-failure"]


class IntermittentNiCleanup(NeedinfoCleanup):
    def __init__(self) -> None:
        super().__init__()
        self.days_since_resolved = self.get_config("days_since_resolved", 7)

    def description(self) -> str:
        return "Clear needinfos on resolved intermittent/perma failure bugs"

    def get_bz_params(self, date: str) -> dict[str, Any]:
        resolved_before = lmdutils.get_date_str(
            lmdutils.get_date_ymd(date) - timedelta(days=self.days_since_resolved)
        )
        return {
            "include_fields": [
                "flags",
                "status",
                "resolution",
                "keywords",
                "cf_last_resolved",
            ],
            "status": CLOSED_STATUSES,
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

    @staticmethod
    def get_stale_needinfos(bug: Bug) -> list[dict[str, Any]]:
        last_resolved = bug.get("cf_last_resolved")
        if not last_resolved:
            return []
        last_resolved = lmdutils.get_date_ymd(last_resolved)

        # Needinfos requested (or redirected to someone else) after the bug
        # was resolved were likely intentional, so we leave them alone.
        return [
            flag
            for flag in NeedinfoCleanup.get_pending_needinfos(bug)
            if lmdutils.get_date_ymd(flag["modification_date"]) < last_resolved
        ]

    def get_needinfos_to_clear(
        self, bug: Bug
    ) -> tuple[list[dict[str, Any]], str | None]:
        if bug["status"] not in CLOSED_STATUSES:
            return [], None
        if not set(bug.get("keywords", [])) & set(FAILURE_KEYWORDS):
            return [], None
        return (
            self.get_stale_needinfos(bug),
            "Clearing the needinfo request since this test failure bug has been resolved.",
        )


if __name__ == "__main__":
    IntermittentNiCleanup().run()
