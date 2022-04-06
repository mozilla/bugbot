# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils

from auto_nag import people, utils
from auto_nag.bzcleaner import BzCleaner


class AssigneeNoLogin(BzCleaner):
    def __init__(self):
        super(AssigneeNoLogin, self).__init__()
        self.unassign_weeks = utils.get_config(self.name(), "unassign_weeks", 2)
        self.nmonths = utils.get_config(self.name(), "number_of_months", 12)
        self.max_ni = utils.get_config(self.name(), "max_ni")
        self.autofix_assignee = {}
        self.default_assignees = utils.get_default_assignees()
        self.people = people.People.get_instance()

    def description(self):
        return "Open and assigned bugs where the assignee's last login was more than {} months ago".format(
            self.nmonths
        )

    def has_product_component(self):
        return True

    def has_assignee(self):
        return True

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def get_extra_for_template(self):
        return {"nmonths": self.nmonths}

    def columns(self):
        return ["triage_owner", "component", "id", "summary", "assignee"]

    def handle_bug(self, bug, data):
        assignee = bug["assigned_to"]
        if self.people.is_mozilla(assignee):
            return None

        bugid = str(bug["id"])

        do_needinfo = True

        # Avoid to ni everyday...
        if self.has_bot_set_ni(bug):
            do_needinfo = False

        # Avoid to ni if the bug has low priority and low severity.
        # It's not paramount for triage owners to make an explicit decision here, it's enough for them
        # to receive the notification about the unassignment from Bugzilla via email.
        if bug["priority"] in ("--", "P3", "P4", "P5") and bug["severity"] in (
            "S3",
            "normal",
            "S4",
            "minor",
            "trivial",
            "enhancement",
        ):
            do_needinfo = False

        if do_needinfo and not self.add_auto_ni(
            bugid,
            {
                "mail": bug["triage_owner"],
                "nickname": bug["triage_owner_detail"]["nick"],
            },
        ):
            # Don't unassign if we can't needinfo.
            return None

        data[bugid] = {"triage_owner": bug["triage_owner_detail"]["real_name"]}
        prod = bug["product"]
        comp = bug["component"]
        default_assignee = self.default_assignees[prod][comp]
        self.autofix_assignee[bugid] = {"assigned_to": default_assignee}
        if not do_needinfo:
            self.autofix_assignee[bugid]["comment"] = {
                "body": f"The bug assignee didn't login in Bugzilla in the last { self.nmonths } months, so the assignee is being reset."
            }
        return bug

    def get_bz_params(self, date):
        date = lmdutils.get_date_ymd(date)
        start_date = date - relativedelta(months=self.nmonths)
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
            "f1": "assignee_last_login",
            "o1": "lessthan",
            "v1": start_date,
            "n3": "1",
            "f3": "assigned_to",
            "o3": "changedafter",
            "v3": f"-{self.unassign_weeks}w",
        }

        utils.get_empty_assignees(params, negation=True)

        return params

    def get_autofix_change(self):
        return self.autofix_assignee


if __name__ == "__main__":
    AssigneeNoLogin().run()
