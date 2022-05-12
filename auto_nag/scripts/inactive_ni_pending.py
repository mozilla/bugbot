# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.user_activity import UserActivity

RECENT_BUG_LIMIT = lmdutils.get_date_ymd("today") - relativedelta(months=6)

# TODO: should be moved when resolving https://github.com/mozilla/relman-auto-nag/issues/1384
HIGH_PRIORITY = {"P1", "P2"}
HIGH_SEVERITY = {"S1", "critical", "S2", "major"}


class InactiveNeedinfoPending(BzCleaner):
    def __init__(self):
        super(InactiveNeedinfoPending, self).__init__()
        self.max_actions = utils.get_config(self.name(), "max_actions", 7)

    def get_max_actions(self):
        return self.max_actions

    def description(self):
        return "Bugs with needinfo pending on inactive people"

    def columns(self):
        return ["id", "summary", "inactive_ni", "inactive_ni_count"]

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

        Note: This method will mutate the provided bug objects and will return a new `bugs`
        dictionary.
        """
        requestee_bugs = defaultdict(list)
        for bugid, bug in bugs.items():
            for flag in bug["needinfo_flags"]:
                if "requestee" not in flag:
                    flag["requestee"] = ""

                requestee_bugs[flag["requestee"]].append(bugid)

        triage_owners = {bug["triage_owner"] for bug in bugs.values()}

        user_activity = UserActivity()
        inactive_users = user_activity.check_users(
            set(requestee_bugs.keys()) | triage_owners
        )
        inactive_requestee_bugs = {
            bugid
            for requestee, bugids in requestee_bugs.items()
            if requestee in inactive_users
            for bugid in bugids
        }

        bugs = {
            bugid: bug
            for bugid, bug in bugs.items()
            if bugid in inactive_requestee_bugs
            and bug["triage_owner"] not in inactive_users
        }

        for bug in bugs.values():
            bug["inactive_ni"] = [
                {
                    "id": flag["id"],
                    "requestee": flag["requestee"],
                    "requestee_status": user_activity.get_string_status(
                        inactive_users[flag["requestee"]]
                    ),
                }
                for flag in bug["needinfo_flags"]
                if flag["requestee"] in inactive_users
            ]
            bug["inactive_ni_count"] = len(bug["inactive_ni"])
            self.add_action(bug)

        return bugs

    @staticmethod
    def should_forward_needinfo(bug):
        """
        Determain if the bug is important enough to have the needinfos forwarded
        to the triage owner.
        """

        return (
            bug["priority"] in HIGH_PRIORITY
            or bug["severity"] in HIGH_SEVERITY
            or lmdutils.get_date_ymd(bug["creation_time"]) >= RECENT_BUG_LIMIT
        )

    def add_action(self, bug):
        users_num = len(set([flag["requestee"] for flag in bug["inactive_ni"]]))

        if self.should_forward_needinfo(bug):
            autofix = {
                "flags": [
                    {
                        "id": flag["id"],
                        "status": "?",
                        "requestee": bug["triage_owner"],
                    }
                    for flag in bug["inactive_ni"]
                ],
                "comment": {
                    "body": f"Redirect needinfo pending on inactive {utils.plural('user', users_num)} to the triage owner.",
                },
            }
        else:
            autofix = {
                "flags": [
                    {
                        "id": flag["id"],
                        "status": "X",
                    }
                    for flag in bug["inactive_ni"]
                ],
                "comment": {
                    "body": f"Clear needinfo pending on inactive {utils.plural('user', users_num)}.",
                },
            }

        self.add_prioritized_action(bug, bug["triage_owner"], autofix=autofix)

    def get_bug_sort_key(self, bug):
        return (
            not self.should_forward_needinfo(bug),
            utils.get_sort_by_bug_importance_key(bug),
        )

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "priority": bug["priority"],
            "severity": bug["severity"],
            "creation_time": bug["creation_time"],
            "triage_owner": bug["triage_owner"],
            "needinfo_flags": [
                flag for flag in bug["flags"] if flag["name"] == "needinfo"
            ],
        }

        return bug

    def get_bz_params(self, date):
        date = lmdutils.get_date_ymd(date)

        fields = [
            "triage_owner",
            "flags",
            "priority",
            "severity",
            "creation_time",
        ]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "flagtypes.name",
            "o1": "equals",
            "v1": "needinfo?",
        }

        # Run monthly on all bugs and weekly on recently changed bugs
        if date.day > 7:
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
