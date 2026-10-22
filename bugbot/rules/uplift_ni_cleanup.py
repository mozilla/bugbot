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

# Prefix of the attachment flags used to request an uplift, e.g.
# `approval-mozilla-beta` or `approval-mozilla-esr140`.
APPROVAL_FLAG_PREFIX = "approval-mozilla-"


class UpliftNiCleanup(NeedinfoCleanup):
    def description(self) -> str:
        return (
            "Clear uplift needinfos once an uplift was requested or, on closed "
            "bugs, once no Firefox version is affected anymore"
        )

    def has_last_comment_time(self) -> bool:
        return True

    def get_bz_params(self, date: str) -> dict[str, Any]:
        return {
            "include_fields": [
                "flags",
                "resolution",
                "cf_last_resolved",
                "attachments.flags",
                "_custom",
            ],
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
            # Either the bug is closed or an uplift was requested on it.
            "j7": "OR",
            "f7": "OP",
            "f8": "bug_status",
            "o8": "anyexact",
            "v8": ",".join(CLOSED_STATUSES),
            "f9": "flagtypes.name",
            "o9": "substring",
            "v9": APPROVAL_FLAG_PREFIX,
            "f10": "CP",
        }

    def commenthandler(self, bug: Bug, bugid: str | int, data: dict[str, Any]) -> None:
        data[str(bugid)]["comments"] = bug["comments"]

    @staticmethod
    def get_approval_request_times(bug: Bug) -> list[str]:
        return [
            flag["creation_date"]
            for attachment in bug.get("attachments", [])
            for flag in attachment.get("flags", [])
            if flag["name"].startswith(APPROVAL_FLAG_PREFIX)
        ]

    def get_needinfos_to_clear(
        self, bug: Bug
    ) -> tuple[list[dict[str, Any]], str | None]:
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
        if not needinfos:
            return [], None

        # The needinfo asks for an uplift decision, so it is answered as soon
        # as an uplift is requested after it, whatever happens to the bug.
        approval_times = self.get_approval_request_times(bug)
        answered = [
            flag
            for flag in needinfos
            if any(time >= flag["creation_date"] for time in approval_times)
        ]
        if answered:
            return (
                answered,
                "Clearing the uplift needinfo request since an uplift has been "
                "requested.",
            )

        if not bug["resolution"]:
            return [], None

        if any(
            field.startswith("cf_status_firefox") and value in AFFECTED_STATUSES
            for field, value in bug.items()
        ):
            return [], None

        return (
            needinfos,
            "Clearing the uplift needinfo request since this bug is closed and "
            "no Firefox version is marked as affected anymore.",
        )


if __name__ == "__main__":
    UpliftNiCleanup().run()
