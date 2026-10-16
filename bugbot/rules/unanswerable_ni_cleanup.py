# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Any

from libmozdata.bugzilla import BugzillaUser

from bugbot import utils
from bugbot.bzcleaner import Bug
from bugbot.needinfo_cleanup import NeedinfoCleanup


class UnanswerableNiCleanup(NeedinfoCleanup):
    def __init__(self) -> None:
        super().__init__()
        self.disabled_users: set[str] = set()

    def description(self) -> str:
        return "Clear needinfos requested from accounts that cannot answer"

    def get_bz_params(self, date: str) -> dict[str, Any]:
        return {
            "include_fields": ["flags", "resolution", "cf_last_resolved"],
            "f1": "flagtypes.name",
            "o1": "substring",
            "v1": "needinfo?",
        }

    def get_disabled_users(self, names: set[str]) -> set[str]:
        def handler(user: dict[str, Any], data: set[str]) -> None:
            if not user["can_login"]:
                data.add(user["name"])

        disabled: set[str] = set()
        BugzillaUser(
            user_names=sorted(names),
            include_fields=["name", "can_login"],
            user_handler=handler,
            user_data=disabled,
        ).wait()
        return disabled

    def prepare(self, bugs: dict[str, Bug]) -> None:
        # Needinfos pending on disabled accounts in open bugs are redirected to
        # the triage owner by the inactive_ni_pending rule, so we only look at
        # closed bugs here.
        names = {
            flag["requestee"]
            for bug in bugs.values()
            if bug["resolution"]
            for flag in self.get_pending_needinfos(bug)
            if flag.get("requestee") and not utils.is_bot_email(flag["requestee"])
        }
        self.disabled_users = self.get_disabled_users(names) if names else set()

    def is_unanswerable(self, bug: Bug, requestee: str | None) -> bool:
        if not requestee:
            return False
        if utils.is_bot_email(requestee):
            return True
        return bool(bug["resolution"]) and requestee in self.disabled_users

    def get_needinfos_to_clear(
        self, bug: Bug
    ) -> tuple[list[dict[str, Any]], str | None]:
        needinfos = [
            flag
            for flag in self.get_pending_needinfos(bug)
            if self.is_unanswerable(bug, flag.get("requestee"))
        ]
        return (
            needinfos,
            "Clearing the needinfo request since it is pending on an account that "
            "cannot answer (a bot, a component watcher, or a disabled account).",
        )


if __name__ == "__main__":
    UnanswerableNiCleanup().run()
