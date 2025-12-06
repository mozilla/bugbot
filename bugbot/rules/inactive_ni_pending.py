# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
from datetime import timedelta
from enum import IntEnum, auto

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.constants import HIGH_PRIORITY, HIGH_SEVERITY, SECURITY_KEYWORDS
from bugbot.user_activity import UserActivity, UserStatus
from bugbot.utils import plural

RECENT_BUG_LIMIT = lmdutils.get_date("today", timedelta(weeks=5).days)
RECENT_NEEDINFO_LIMIT = lmdutils.get_date("today", timedelta(weeks=2).days)


class NeedinfoAction(IntEnum):
    FORWARD = auto()
    CLEAR = auto()
    CLOSE_BUG = auto()

    def __str__(self):
        return self.name.title().replace("_", " ")


class InactiveNeedinfoPending(BzCleaner):
    normal_changes_max: int = 100

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

        # Resolving https://github.com/mozilla/bugbot/issues/1300 should clean this
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

        user_activity = UserActivity(include_fields=["groups", "creation_time"])
        needinfo_requestees = set(requestee_bugs.keys())
        triage_owners = {bug["triage_owner"] for bug in bugs.values()}
        inactive_users = user_activity.check_users(
            needinfo_requestees | triage_owners, ignore_bots=True
        )

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
                    "setter": flag["setter"],
                    "requestee": flag["requestee"],
                    "requestee_status": user_activity.get_string_status(
                        inactive_users[flag["requestee"]]["status"],
                    ),
                    "requestee_canconfirm": has_canconfirm_group(flag["requestee"]),
                }
                for flag in bug["needinfo_flags"]
                if flag["requestee"] in inactive_users
                and (
                    # Exclude recent needinfos to allow some time for external
                    # users to respond.
                    flag["modification_date"] < RECENT_NEEDINFO_LIMIT
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
            or bug["last_change_time"] >= RECENT_BUG_LIMIT
            or any(keyword in SECURITY_KEYWORDS for keyword in bug["keywords"])
        ):
            return NeedinfoAction.FORWARD

        if (
            len(bug["needinfo_flags"]) == 1
            and bug["type"] == "defect"
            and inactive_ni[0]["requestee"] == bug["creator"]
            and not inactive_ni[0]["requestee_canconfirm"]
            and not any(
                attachment["content_type"] == "text/x-phabricator-request"
                and not attachment["is_obsolete"]
                for attachment in bug["attachments"]
            )
            and not was_unconfirmed(bug)
        ):
            return NeedinfoAction.CLOSE_BUG

        if bug["severity"] == "--":
            return NeedinfoAction.FORWARD

        return NeedinfoAction.CLEAR

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

    @staticmethod
    def _request_from_triage_owner(bug):
        reasons = []
        if bug["priority"] in HIGH_PRIORITY:
            reasons.append("high priority")
        if bug["severity"] in HIGH_SEVERITY:
            reasons.append("high severity")
        if bug["last_change_time"] >= RECENT_BUG_LIMIT:
            reasons.append("recent activity")

        if len(reasons) == 0 and bug["severity"] == "--" and bug["type"] == "defect":
            return "since the bug doesn't have a severity set, could you please set the severity or close the bug?"

        comment = []
        if reasons:
            comment.append(f"since the bug has {utils.english_list(reasons)}")

        if (
            len(bug["inactive_ni"]) == 1
            and bug["inactive_ni"][0]["setter"] == bug["triage_owner"]
        ):
            comment.append(
                "could you please find another way to get the information or close the bug as `INCOMPLETE` if it is not actionable?"
            )
        else:
            comment.append("could you have a look please?")

        return ", ".join(comment)

    def add_action(self, bug):
        users_num = len(set([flag["requestee"] for flag in bug["inactive_ni"]]))

        if bug["action"] == NeedinfoAction.FORWARD:
            autofix = {
                "flags": (
                    self._clear_inactive_ni_flags(bug)
                    + self._needinfo_triage_owner_flag(bug)
                ),
                "comment": {
                    "body": (
                        f'Redirect { plural("a needinfo that is", bug["inactive_ni"], "needinfos that are") } pending on { plural("an inactive user", users_num, "inactive users") } to the triage owner.'
                        f'\n:{ bug["triage_owner_nic"] }, {self._request_from_triage_owner(bug)}'
                    )
                },
            }

        elif bug["action"] == NeedinfoAction.CLEAR:
            autofix = {
                "flags": self._clear_inactive_ni_flags(bug),
                "comment": {
                    "body": (
                        f'Clear { plural("a needinfo that is", bug["inactive_ni"], "needinfos that are") } pending on { plural("an inactive user", users_num, "inactive users") }.'
                        "\n\nInactive users most likely will not respond; "
                        "if the missing information is essential and cannot be collected another way, "
                        "the bug maybe should be closed as `INCOMPLETE`."
                    ),
                },
            }

        elif bug["action"] == NeedinfoAction.CLOSE_BUG:
            autofix = {
                "flags": self._clear_inactive_ni_flags(bug),
                "status": "RESOLVED",
                "resolution": "INCOMPLETE",
                "comment": {
                    "body": (
                        "A needinfo is requested from the reporter, however, the reporter is inactive on Bugzilla. "
                        "Given that the bug is still `UNCONFIRMED`, closing the bug as incomplete."
                    )
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
            bug["triage_owner_detail"]["nick"] if "triage_owner_detail" in bug else ""
        )
        data[bugid] = {
            "priority": bug["priority"],
            "severity": bug["severity"],
            "creation_time": bug["creation_time"],
            "last_change_time": utils.get_last_no_bot_comment_date(bug),
            "creator": bug["creator"],
            "type": bug["type"],
            "attachments": bug["attachments"],
            "triage_owner": bug["triage_owner"],
            "triage_owner_nic": triage_owner_nic,
            "is_confirmed": bug["is_confirmed"],
            "needinfo_flags": [
                flag for flag in bug["flags"] if flag["name"] == "needinfo"
            ],
            "keywords": bug["keywords"],
        }

        return bug

    def get_bz_params(self, date):
        fields = [
            "type",
            "attachments.content_type",
            "attachments.is_obsolete",
            "triage_owner",
            "flags",
            "priority",
            "severity",
            "creation_time",
            "comments",
            "creator",
            "keywords",
            "is_confirmed",
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


def was_unconfirmed(bug: dict) -> bool:
    """Check if a bug was unconfirmed.

    Returns:
        True if the bug was unconfirmed and now is confirmed, False otherwise.
    """
    if not bug["is_confirmed"]:
        return False

    had_unconfirmed_status = False

    def check_unconfirmed_in_history(bug):
        nonlocal had_unconfirmed_status
        for history in bug["history"]:
            for change in history["changes"]:
                if change["field_name"] == "status":
                    if change["removed"] == "UNCONFIRMED":
                        had_unconfirmed_status = True
                        return
                    break

    if "history" in bug:
        check_unconfirmed_in_history(bug)
    else:
        Bugzilla(bug["id"], historyhandler=check_unconfirmed_in_history).wait()

    return had_unconfirmed_status


if __name__ == "__main__":
    InactiveNeedinfoPending().run()
