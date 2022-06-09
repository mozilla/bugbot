# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import collections

from libmozdata import utils as lmdutils

from auto_nag import people, utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.user_activity import UserActivity

HIGH_PRIORITY = {"P1", "P2"}
HIGH_SEVERITY = {"S1", "critical", "S2", "major"}


class AssigneeNoLogin(BzCleaner):
    def __init__(self):
        super(AssigneeNoLogin, self).__init__()
        self.unassign_weeks = utils.get_config(self.name(), "unassign_weeks", 2)
        self.max_ni = utils.get_config(self.name(), "max_ni")
        self.max_actions = utils.get_config(self.name(), "max_actions")
        self.default_assignees = utils.get_default_assignees()
        self.people = people.People.get_instance()
        self.unassign_count = collections.defaultdict(int)

        self.extra_ni = {}

    def description(self):
        return "Open and assigned bugs where the assignee is inactive"

    def has_product_component(self):
        return True

    def has_assignee(self):
        return True

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def get_extra_for_template(self):
        return self.extra_ni

    def columns(self):
        return [
            "triage_owner_name",
            "component",
            "id",
            "summary",
            "assignee",
            "assignee_status",
        ]

    def get_max_ni(self):
        return self.max_ni

    def get_max_actions(self):
        return self.max_actions

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        bugs = self.handle_inactive_assignees(bugs)

        # Resolving https://github.com/mozilla/relman-auto-nag/issues/1300 should clean this
        # including improve the wording in the template (i.e., "See the search query on Bugzilla").
        self.query_url = utils.get_bz_search_url({"bug_id": ",".join(bugs.keys())})

        return bugs

    def handle_inactive_assignees(self, bugs):
        user_activity = UserActivity()
        assignees = {bug["assigned_to"] for bug in bugs.values()}
        triage_owners = {bug["triage_owner"] for bug in bugs.values()}
        inactive_users = user_activity.check_users(assignees | triage_owners)

        res = {}
        for bugid, bug in bugs.items():
            if (
                bug["assigned_to"] not in inactive_users
                # If we don't have an active triage owner, we need to wait until
                # we have one before doing anything.
                or bug["triage_owner"] in inactive_users
            ):
                continue

            bug["assignee_status"] = user_activity.get_string_status(
                inactive_users[bug["assigned_to"]]["status"]
            )
            self.add_action(bug)
            res[bugid] = bug

        return res

    def add_action(self, bug):
        prod = bug["product"]
        comp = bug["component"]
        default_assignee = self.default_assignees[prod][comp]
        autofix = {"assigned_to": default_assignee}

        # Avoid to ni if the bug has low priority and low severity.
        # It's not paramount for triage owners to make an explicit decision here, it's enough for them
        # to receive the notification about the unassignment from Bugzilla via email.
        if (
            bug["priority"] not in HIGH_PRIORITY
            and bug["severity"] not in HIGH_SEVERITY
        ):
            needinfo = None
            autofix["comment"] = {
                "body": "The bug assignee is inactive on Bugzilla, so the assignee is being reset."
            }
        else:
            reason = []
            if bug["priority"] in HIGH_PRIORITY:
                reason.append("priority '{}'".format(bug["priority"]))
            if bug["severity"] in HIGH_SEVERITY:
                reason.append("severity '{}'".format(bug["severity"]))

            needinfo = {
                "mail": bug["triage_owner"],
                "nickname": bug["triage_owner_nick"],
                "extra": {"reason": "/".join(reason)},
            }

        self.add_prioritized_action(bug, bug["triage_owner"], needinfo, autofix)

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "assigned_to": bug["assigned_to"],
            "triage_owner": bug["triage_owner"],
            "triage_owner_name": utils.get_name_from_user_detail(
                bug["triage_owner_detail"]
            ),
            "triage_owner_nick": bug["triage_owner_detail"]["nick"],
            "priority": bug["priority"],
            "severity": bug["severity"],
        }

        return bug

    def get_bug_sort_key(self, *args, **kwargs):
        return utils.get_sort_by_bug_importance_key(*args, **kwargs)

    def get_bz_params(self, date):
        date = lmdutils.get_date_ymd(date)
        fields = [
            "assigned_to",
            "triage_owner",
            "flags",
            "priority",
            "severity",
        ]
        params = {
            "include_fields": fields,
            "resolution": "---",
            "n3": "1",
            "f3": "assigned_to",
            "o3": "changedafter",
            "v3": f"-{self.unassign_weeks}w",
        }

        utils.get_empty_assignees(params, negation=True)

        return params


if __name__ == "__main__":
    AssigneeNoLogin().run()
