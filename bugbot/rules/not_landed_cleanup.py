# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Any

from bugbot import utils
from bugbot.bzcleaner import Bug, BzCleaner
from bugbot.rules.not_landed import NOT_LANDED_COMMENT_MARKER

CLOSED_STATUSES = {"RESOLVED", "VERIFIED", "CLOSED"}


class NotLandedCleanup(BzCleaner):
    def description(self) -> str:
        return "Clear not_landed needinfos on bugs resolved as fixed"

    def filter_no_nag_keyword(self) -> bool:
        return False

    def has_last_comment_time(self) -> bool:
        return True

    def get_bz_params(self, date: str) -> dict[str, Any]:
        return {
            "include_fields": ["flags", "status", "resolution"],
            "status": sorted(CLOSED_STATUSES),
            "resolution": "FIXED",
            "f1": "flagtypes.name",
            "o1": "substring",
            "v1": "needinfo?",
            "f2": "setters.login_name",
            "o2": "anyexact",
            "v2": ",".join(utils.get_config("common", "bot_bz_mail")),
            "f3": "longdesc",
            "o3": "casesubstring",
            "v3": NOT_LANDED_COMMENT_MARKER,
        }

    def handle_bug(self, bug: Bug, data: dict[str, Any]) -> Bug:
        data[str(bug["id"])] = {
            "flags": bug["flags"],
            "status": bug["status"],
            "resolution": bug["resolution"],
        }
        return bug

    def commenthandler(self, bug: Bug, bugid: str | int, data: dict[str, Any]) -> None:
        data[str(bugid)]["comments"] = bug["comments"]

    @staticmethod
    def get_not_landed_needinfos(bug: Bug) -> list[dict[str, Any]]:
        bot_accounts = utils.get_config("common", "bot_bz_mail")
        comment_times = {
            comment["creation_time"]
            for comment in bug.get("comments", [])
            if comment["creator"] in bot_accounts
            and NOT_LANDED_COMMENT_MARKER in comment["text"]
        }
        return [
            flag
            for flag in bug.get("flags", [])
            if flag["name"] == "needinfo"
            and flag["status"] == "?"
            and flag["setter"] in bot_accounts
            and flag["creation_date"] in comment_times
        ]

    def get_bugs(
        self,
        date: str = "today",
        bug_ids: list[int] = [],
        chunk_size: int | None = None,
    ) -> dict[str, Any]:
        bugs = super().get_bugs(date=date, bug_ids=bug_ids, chunk_size=chunk_size)
        self.autofix_changes = {}
        for bugid in sorted(bugs, key=int):
            bug = bugs[bugid]
            if bug["status"] not in CLOSED_STATUSES or bug["resolution"] != "FIXED":
                continue
            needinfos = self.get_not_landed_needinfos(bug)
            if not needinfos:
                continue
            self.autofix_changes[bugid] = {
                "flags": [{"id": flag["id"], "status": "X"} for flag in needinfos]
            }
            if len(self.autofix_changes) >= self.normal_changes_max:
                break
        return {bugid: bugs[bugid] for bugid in self.autofix_changes}

    def get_email_data(self, date: str) -> list[Any]:
        # Run the autofix pipeline without sending a summary email.
        super().get_email_data(date)
        return []


if __name__ == "__main__":
    NotLandedCleanup().run()
