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
        self.nmonths = utils.get_config(self.name(), "number_of_months", 12)
        self.last_activity_months = utils.get_config(
            self.name(), "last_activity_months", 3
        )
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
        data[bugid] = {"triage_owner": bug["triage_owner_detail"]["real_name"]}
        prod = bug["product"]
        comp = bug["component"]
        default_assignee = self.default_assignees[prod][comp]
        self.autofix_assignee[bugid] = {"assigned_to": default_assignee}
        return bug

    def get_mail_to_auto_ni(self, bug):
        # Avoid to ni everyday...
        if self.has_bot_set_ni(bug):
            return None

        mail = bug["triage_owner"]
        nick = bug["triage_owner_detail"]["nick"]
        return {"mail": mail, "nickname": nick}

    def get_bz_params(self, date):
        date = lmdutils.get_date_ymd(date)
        start_date = date - relativedelta(months=self.nmonths)
        fields = ["assigned_to", "triage_owner", "flags"]
        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "assignee_last_login",
            "o1": "lessthan",
            "v1": start_date,
            "f2": "days_elapsed",
            "o2": "lessthan",
            "v2": self.last_activity_months * 30,
            "n3": "1",
            "f3": "assigned_to",
            "o3": "changedafter",
            "v3": f"-{self.last_activity_months}m",
        }

        utils.get_empty_assignees(params, negation=True)

        return params

    def get_autofix_change(self):
        return self.autofix_assignee


if __name__ == "__main__":
    AssigneeNoLogin().run()
