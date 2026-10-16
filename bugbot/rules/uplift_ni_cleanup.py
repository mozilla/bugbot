# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Any

from bugbot import utils
from bugbot.bzcleaner import Bug
from bugbot.needinfo_cleanup import CLOSED_STATUSES, NeedinfoCleanup
from bugbot.rules.uplift_beta import (
    AFFECTED_STATUSES,
    COMMENT_MARKER,
    LEGACY_COMMENT_MARKER,
)

UPLIFT_MARKERS = [COMMENT_MARKER, LEGACY_COMMENT_MARKER]


class UpliftNiCleanup(NeedinfoCleanup):
    def description(self) -> str:
        return "Clear uplift needinfos on closed bugs no longer affecting any Firefox version"

    def has_last_comment_time(self) -> bool:
        return True

    def get_bz_params(self, date: str) -> dict[str, Any]:
        return {
            "include_fields": ["flags", "resolution", "cf_last_resolved", "_custom"],
            "bug_status": CLOSED_STATUSES,
            "f1": "flagtypes.name",
            "o1": "substring",
            "v1": "needinfo?",
            "f2": "setters.login_name",
            "o2": "anyexact",
            "v2": ",".join(utils.get_config("common", "bot_bz_mail")),
            "j3": "OR",
            "f3": "OP",
            "f4": "longdesc",
            "o4": "casesubstring",
            "v4": COMMENT_MARKER,
            "f5": "longdesc",
            "o5": "casesubstring",
            "v5": LEGACY_COMMENT_MARKER,
            "f6": "CP",
        }

    def commenthandler(self, bug: Bug, bugid: str | int, data: dict[str, Any]) -> None:
        data[str(bugid)]["comments"] = bug["comments"]

    def get_needinfos_to_clear(
        self, bug: Bug
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not bug["resolution"]:
            return [], None

        if any(
            field.startswith("cf_status_firefox") and value in AFFECTED_STATUSES
            for field, value in bug.items()
        ):
            return [], None

        bot_accounts = utils.get_config("common", "bot_bz_mail")
        uplift_comment_times = {
            comment["creation_time"]
            for comment in bug.get("comments", [])
            if comment["creator"] in bot_accounts
            and any(marker in comment["text"] for marker in UPLIFT_MARKERS)
        }
        needinfos = [
            flag
            for flag in self.get_pending_needinfos(bug)
            if flag["setter"] in bot_accounts
            and flag["creation_date"] in uplift_comment_times
        ]
        return (
            needinfos,
            "Clearing the uplift needinfo request since this bug is closed and "
            "no Firefox version is marked as affected anymore.",
        )


if __name__ == "__main__":
    UpliftNiCleanup().run()
