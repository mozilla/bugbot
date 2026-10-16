# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import timedelta
from typing import Any, Mapping

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils

from bugbot import utils
from bugbot.bzcleaner import Bug, BzCleaner

CLOSED_STATUSES = ["RESOLVED", "VERIFIED", "CLOSED"]

# Bugs closed for longer than this are updated without sending bugmail.
SILENT_AFTER = timedelta(days=365)


class NeedinfoCleanup(BzCleaner):
    """Base class for rules clearing needinfos that are no longer useful.

    Subclasses implement `get_bz_params` and `get_needinfos_to_clear`. Each
    selected bug gets its needinfos cleared with a comment explaining why.
    """

    normal_changes_max: int = 500

    def __init__(self) -> None:
        super().__init__()
        self.date = lmdutils.get_date_ymd("today")
        self.silent_bugids: set[str] = set()

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_default_products(self) -> bool:
        return False

    def handle_bug(self, bug: Bug, data: dict[str, Any]) -> Bug:
        data[str(bug["id"])] = dict(bug)
        return bug

    def is_closed_before(self, bug: Bug, delta: timedelta) -> bool:
        """Check whether the bug was closed more than `delta` before the run date."""
        return bool(
            bug.get("resolution")
            and bug.get("cf_last_resolved")
            and lmdutils.get_date_ymd(bug["cf_last_resolved"]) < self.date - delta
        )

    def time_since(self, timestamp: str) -> str:
        """Format the time elapsed since `timestamp`, e.g. "2 years, 3 months and 5 days"."""
        delta = relativedelta(self.date.date(), lmdutils.get_date_ymd(timestamp).date())
        parts = [
            f"{value} {utils.plural(unit, value)}"
            for unit, value in (
                ("year", delta.years),
                ("month", delta.months),
                ("day", delta.days),
            )
            if value > 0
        ]
        return utils.english_list(parts) if parts else "less than a day"

    def is_older_than(self, timestamp: str, delta: timedelta) -> bool:
        return lmdutils.get_date_ymd(timestamp) < self.date - delta

    @staticmethod
    def get_pending_needinfos(bug: Bug) -> list[dict[str, Any]]:
        return [
            flag
            for flag in bug.get("flags", [])
            if flag["name"] == "needinfo" and flag["status"] == "?"
        ]

    def prepare(self, bugs: dict[str, Bug]) -> None:
        """Fetch any extra data needed by `get_needinfos_to_clear`."""

    def get_needinfos_to_clear(
        self, bug: Bug
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Return the needinfo flags to clear and the reason to put in the comment."""
        raise NotImplementedError

    def get_bugs(
        self,
        date: str = "today",
        bug_ids: list[int] = [],
        chunk_size: int | None = None,
    ) -> dict[str, Any]:
        self.date = lmdutils.get_date_ymd(date)
        bugs = super().get_bugs(date=date, bug_ids=bug_ids, chunk_size=chunk_size)
        self.prepare(bugs)

        self.autofix_changes = {}
        self.silent_bugids = set()
        doc = self.get_documentation()
        for bugid in sorted(bugs, key=int):
            bug = bugs[bugid]
            needinfos, reason = self.get_needinfos_to_clear(bug)
            if not needinfos:
                continue
            self.autofix_changes[bugid] = {
                "flags": [{"id": flag["id"], "status": "X"} for flag in needinfos],
                "comment": {"body": f"{reason}\n\n{doc}"},
            }
            if self.is_closed_before(bug, SILENT_AFTER):
                self.silent_bugids.add(bugid)
            if len(self.autofix_changes) >= self.normal_changes_max:
                break
        return {bugid: bugs[bugid] for bugid in self.autofix_changes}

    # Called through `self` by `BzCleaner.autofix`, so overriding the static
    # method lets us choose the account (and thus whether bugmail is sent) per bug.
    def apply_changes_on_bugzilla(  # type: ignore[override]
        self,
        rule_name: str,
        new_changes: Mapping[str, dict],
        no_bugmail: bool = False,
        is_dryrun: bool = True,
        db_extra: Mapping[str, Any] | None = None,
    ) -> None:
        silent = {k: v for k, v in new_changes.items() if k in self.silent_bugids}
        loud = {k: v for k, v in new_changes.items() if k not in self.silent_bugids}
        for changes, quiet in ((silent, True), (loud, no_bugmail)):
            if changes:
                BzCleaner.apply_changes_on_bugzilla(
                    rule_name, changes, quiet, is_dryrun, db_extra
                )

    def get_email_data(self, date: str) -> list[Any]:
        # Run the autofix pipeline without sending a summary email.
        super().get_email_data(date)
        return []
