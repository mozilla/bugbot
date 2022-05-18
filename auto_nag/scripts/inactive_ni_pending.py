# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
from datetime import timedelta
from enum import IntEnum, auto

from libmozdata import utils as lmdutils

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.user_activity import UserActivity, UserStatus
from auto_nag.utils import plural

RECENT_BUG_LIMIT = lmdutils.get_date("today", timedelta(weeks=26).days)
RECENT_NEEINFO_LIMIT = lmdutils.get_date("today", timedelta(weeks=3).days)

# TODO: should be moved when resolving https://github.com/mozilla/relman-auto-nag/issues/1384
HIGH_PRIORITY = {"P1", "P2"}
HIGH_SEVERITY = {"S1", "critical", "S2", "major"}


class NeedinfoAction(IntEnum):
    FORWARD_NEEDINFO = auto()
    CLEAR_NEEDINFO = auto()
    NEEDINFO_TRIAGE_OWNER = auto()
    CLOSE_BUG = auto()

    def __str__(self):
        return self.name.title().replace("_", " ")


class InactiveNeedinfoPending(BzCleaner):
    def __init__(self):
        super(InactiveNeedinfoPending, self).__init__()
        self.max_actions = utils.get_config(self.name(), "max_actions", 7)

    def get_max_actions(self):
        return self.max_actions

    def description(self):
        return "Bugs with needinfo pending on inactive people"

    def columns(self):
        return [
            "id",
            "summary",
            "inactive_ni",
            "inactive_ni_count",
            "action",
            "triage_owner",
        ]

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        bugs = self.handle_inactive_requestee(bugs)

        # Resolving https://github.com/mozilla/relman-auto-nag/issues/1300 should clean this
        # including improve the wording in the template (i.e., "See the search query on Bugzilla").
        self.query_url = utils.get_bz_search_url({"bug_id": ",".join(bugs.keys())})

        return bugs

    def handle_inactive_requestee(self, bugs):
        """
        Detect inactive users and filter bugs to keep only the ones with needinfo pending on
        inactive users.
        """
        requestee_bugs = defaultdict(list)
        for bugid, bug in bugs.items():
            for flag in bug["needinfo_flags"]:
                if "requestee" not in flag:
                    flag["requestee"] = ""

                requestee_bugs[flag["requestee"]].append(bugid)

        user_activity = UserActivity(include_fields=["groups"])
        needinfo_requestees = set(requestee_bugs.keys())
        triage_owners = {bug["triage_owner"] for bug in bugs.values()}
        inactive_users = user_activity.check_users(needinfo_requestees | triage_owners)

        inactive_requestee_bugs = {
            bugid
            for requestee, bugids in requestee_bugs.items()
            if requestee in inactive_users
            for bugid in bugids
        }

        def has_canconfirm_group(user_email):
            for group in inactive_users[user_email].get("groups", []):
                if group["name"] == "canconfirm":
                    return True
            return False

        def get_inactive_ni(bug):
            return [
                {
                    "id": flag["id"],
                    "requestee": flag["requestee"],
                    "requestee_status": user_activity.get_string_status(
                        inactive_users[flag["requestee"]]["status"]
                    ),
                    "canconfirm": has_canconfirm_group(flag["requestee"]),
                }
                for flag in bug["needinfo_flags"]
                if flag["requestee"] in inactive_users
                and (
                    # Excloud recent needinfos to allow some time for external
                    # users to response.
                    flag["modification_date"] < RECENT_NEEINFO_LIMIT
                    or inactive_users[flag["requestee"]]["status"]
                    in [UserStatus.DISABLED, UserStatus.UNDEFINED]
                )
            ]

        res = {}
        skiplist = self.get_auto_ni_skiplist()
        for bugid, bug in bugs.items():
            if (
                bugid not in inactive_requestee_bugs
                or bug["triage_owner"] in inactive_users
                or bug["triage_owner"] in skiplist
            ):
                continue

            inactive_ni = get_inactive_ni(bug)
            if len(inactive_ni) == 0:
                continue

            bug = {
                **bug,
                "inactive_ni": inactive_ni,
                "inactive_ni_count": len(inactive_ni),
                "action": self.get_action_type(bug, inactive_ni),
            }
            res[bugid] = bug
            self.add_action(bug)

        return res

    @staticmethod
    def get_action_type(bug, inactive_ni):
        """
        Determine if should forward needinfos to the triage owner, clear the
        needinfos, or close the bug.
        """

        if (
            bug["priority"] in HIGH_PRIORITY
            or bug["severity"] in HIGH_SEVERITY
            or bug["creation_time"] >= RECENT_BUG_LIMIT
        ):
            return NeedinfoAction.FORWARD_NEEDINFO

        if bug["severity"] == "--":
            if (
                len(bug["needinfo_flags"]) == 1
                and inactive_ni[0]["requestee"] == bug["creator"]
                and not inactive_ni[0]["canconfirm"]
            ):
                return NeedinfoAction.CLOSE_BUG

            return NeedinfoAction.NEEDINFO_TRIAGE_OWNER

        return NeedinfoAction.CLEAR_NEEDINFO

    @staticmethod
    def _clear_inactive_ni_flags(bug):
        return [
            {
                "id": flag["id"],
                "status": "X",
            }
            for flag in bug["inactive_ni"]
        ]

    @staticmethod
    def _needinfo_triage_owner_flag(bug):
        return [
            {
                "name": "needinfo",
                "requestee": bug["triage_owner"],
                "status": "?",
                "new": "true",
            }
        ]

    def add_action(self, bug):
        users_num = len(set([flag["requestee"] for flag in bug["inactive_ni"]]))

        if bug["action"] == NeedinfoAction.FORWARD_NEEDINFO:
            autofix = {
                "flags": (
                    self._clear_inactive_ni_flags(bug)
                    + self._needinfo_triage_owner_flag(bug)
                ),
                "comment": {
                    "body": (
                        f'Redirect { plural("a needinfo that is", bug["inactive_ni"], "needinfos that are") } pending on { plural("an inactive user", users_num, "inactive users") } to the triage owner.'
                        f'\n:{ bug["triage_owner_nic"] }, could you have a look please?'
                    )
                },
            }

        elif bug["action"] == NeedinfoAction.CLEAR_NEEDINFO:
            autofix = {
                "flags": self._clear_inactive_ni_flags(bug),
                "comment": {
                    "body": f'Clear { plural("a needinfo that is", bug["inactive_ni"], "needinfos that are") } pending on { plural("an inactive user", users_num, "inactive users") }.',
                },
            }

        elif bug["action"] == NeedinfoAction.NEEDINFO_TRIAGE_OWNER:
            autofix = {
                "flags": (
                    self._clear_inactive_ni_flags(bug)
                    + self._needinfo_triage_owner_flag(bug)
                ),
                "comment": {
                    "body": (
                        f'Redirect { plural("a needinfo that is", bug["inactive_ni"], "needinfos that are") } pending on { plural("an inactive user", users_num, "inactive users") } to the triage owner.'
                        f'\n:{ bug["triage_owner_nic"] }, could you please set the severity or close the bug?'
                    )
                },
            }

        elif bug["action"] == NeedinfoAction.CLOSE_BUG:
            autofix = {
                "status": "RESOLVED",
                "resolution": "INCOMPLETE",
                "comment": {
                    "body": "A needinfo is requested from the reporter, however, the reporter is inactive on Bugzilla. Closing the bug as incomplete."
                },
            }

        autofix["comment"]["body"] += f"\n\n{self.get_documentation()}\n"
        self.add_prioritized_action(bug, bug["triage_owner"], autofix=autofix)

    def get_bug_sort_key(self, bug):
        return (
            bug["action"],
            utils.get_sort_by_bug_importance_key(bug),
        )

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        triage_owner_nic = (
            bug["triage_owner_detail"]["nick"] if bug["triage_owner"] in bug else ""
        )
        data[bugid] = {
            "priority": bug["priority"],
            "severity": bug["severity"],
            "creation_time": bug["creation_time"],
            "last_change_time": bug["last_change_time"],
            "creator": bug["creator"],
            "triage_owner": bug["triage_owner"],
            "triage_owner_nic": triage_owner_nic,
            "needinfo_flags": [
                flag for flag in bug["flags"] if flag["name"] == "needinfo"
            ],
        }

        return bug

    def get_bz_params(self, date):
        fields = [
            "triage_owner",
            "flags",
            "priority",
            "severity",
            "creation_time",
            "last_change_time",
            "creator",
        ]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "flagtypes.name",
            "o1": "equals",
            "v1": "needinfo?",
        }

        # Run monthly on all bugs and weekly on recently changed bugs
        if lmdutils.get_date_ymd(date).day > 7:
            params.update(
                {
                    "f2": "anything",
                    "o2": "changedafter",
                    "v2": "-1m",
                }
            )

        return params


if __name__ == "__main__":
    InactiveNeedinfoPending().run()
