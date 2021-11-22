# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import utils as lmdutils

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.escalation import Escalation, NoActivityDays
from auto_nag.nag_me import Nag
from auto_nag.round_robin import RoundRobin


class P1NoAssignee(BzCleaner, Nag):
    def __init__(self):
        super(P1NoAssignee, self).__init__()
        self.escalation = Escalation(
            self.people,
            data=utils.get_config(self.name(), "escalation"),
            skiplist=utils.get_config("workflow", "supervisor_skiplist", []),
        )
        self.round_robin = RoundRobin.get_instance()
        self.components_skiplist = utils.get_config("workflow", "components_skiplist")

    def description(self):
        return "P1 Bugs, no assignee and no activity for few days"

    def nag_template(self):
        return self.template()

    def get_extra_for_template(self):
        return {"ndays": self.ndays}

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def ignore_meta(self):
        return True

    def has_last_comment_time(self):
        return True

    def has_product_component(self):
        return True

    def columns(self):
        return ["component", "id", "summary", "last_comment"]

    def handle_bug(self, bug, data):
        # check if the product::component is in the list
        if utils.check_product_component(self.components_skiplist, bug):
            return None
        return bug

    def get_mail_to_auto_ni(self, bug):
        # For now, disable the needinfo
        return None

        # Avoid to ni everyday...
        if self.has_bot_set_ni(bug):
            return None

        mail, nick = self.round_robin.get(bug, self.date)
        if mail and nick:
            return {"mail": mail, "nickname": nick}

        return None

    def set_people_to_nag(self, bug, buginfo):
        priority = "high"
        if not self.filter_bug(priority):
            return None

        owners = self.round_robin.get(bug, self.date, only_one=False, has_nick=False)
        real_owner = bug["triage_owner"]
        self.add_triage_owner(owners, real_owner=real_owner)
        if not self.add(owners, buginfo, priority=priority):
            self.add_no_manager(buginfo["id"])

        return bug

    def get_bz_params(self, date):
        self.ndays = NoActivityDays(self.name()).get(
            (utils.get_next_release_date() - self.nag_date).days
        )
        self.date = lmdutils.get_date_ymd(date)
        fields = ["triage_owner", "flags"]
        params = {
            "bug_type": "defect",
            "include_fields": fields,
            "resolution": "---",
            "f1": "priority",
            "o1": "equals",
            "v1": "P1",
            "f2": "days_elapsed",
            "o2": "greaterthaneq",
            "v2": self.ndays,
        }

        utils.get_empty_assignees(params)

        return params


if __name__ == "__main__":
    P1NoAssignee().run()
