# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Dict

from libmozdata import utils as lmdutils

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.components import ComponentName
from auto_nag.escalation import Escalation
from auto_nag.nag_me import Nag
from auto_nag.round_robin import RoundRobin

ESCALATION_CONFIG = {
    "normal": {
        "[0;+∞[": {
            "supervisor": "self",
            "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        },
    },
    "high": {
        "[0;+∞[": {
            "supervisor": "n+1",
            "days": ["Mon", "Thu"],
        },
    },
}


class TriagedNoSeverity(BzCleaner, Nag):
    def __init__(
        self,
        inactivity_days: int = 3,
        oldest_bug_days: int = 360,
        normal_escalation_days: int = 14,
        high_escalation_days: int = 28,
    ):
        """Constructor

        Args:
            inactivity_days: number of days that a bug should be inactive before
                being considered.
            oldest_bug_days: the max number of days since the creation of a bug
                to be considered.
            normal_escalation_days: number of days since a bug is triaged to be
                consider for normal escalation.
            high_escalation_days: number of days since a bug is triaged to be
                consider for high escalation.
        """
        super(TriagedNoSeverity, self).__init__()
        self.oldest_bug_days = oldest_bug_days
        self.escalation = Escalation(
            self.people,
            data=ESCALATION_CONFIG,
            skiplist=utils.get_config("workflow", "supervisor_skiplist", []),
        )
        self.round_robin = RoundRobin.get_instance()
        self.components_skiplist = {
            ComponentName.from_str(pc)
            for pc in utils.get_config("workflow", "components_skiplist")
        }

        self.activity_date = lmdutils.get_date("today", inactivity_days)
        self.normal_escalation_date = lmdutils.get_date("today", normal_escalation_days)
        self.high_escalation_date = lmdutils.get_date("today", high_escalation_days)

        # FIXME: This is a workaround to pass the priority to `set_people_to_nag`
        # without altering the bug object.
        self.bug_priority: Dict[str, str] = {}

    def description(self):
        return "Triaged bugs without a severity set"

    def nag_template(self):
        return self.template()

    def nag_preamble(self):
        return True

    def has_product_component(self):
        return True

    def ignore_meta(self):
        return True

    def columns(self):
        return ["component", "id", "summary", "triaged_since"]

    def handle_bug(self, bug, data):
        if (
            ComponentName.from_bug(bug) in self.components_skiplist
            or utils.get_last_no_bot_comment_date(bug) > self.activity_date
        ):
            return None

        triaged_date = utils.get_last_triaged_date(bug)
        if triaged_date < self.high_escalation_date:
            priority = "high"
        elif triaged_date < self.normal_escalation_date:
            priority = "normal"
        else:
            return None

        bugid = str(bug["id"])
        data[bugid] = {
            "triaged_since": utils.get_human_lag(triaged_date),
        }

        self.bug_priority[bugid] = priority
        return bug

    def get_mail_to_auto_ni(self, bug):
        mail, nick = self.round_robin.get(bug, self.date)
        if mail and nick:
            return {"mail": mail, "nickname": nick}

        return None

    def set_people_to_nag(self, bug, buginfo):
        priority = self.bug_priority[buginfo["id"]]
        if priority == "normal":
            return bug

        owners = self.round_robin.get(bug, self.date, only_one=False, has_nick=False)
        real_owner = bug["triage_owner"]
        self.add_triage_owner(owners, real_owner=real_owner)
        if not self.add(owners, buginfo, priority=priority):
            self.add_no_manager(buginfo["id"])
        return bug

    def get_bz_params(self, date):
        fields = [
            "triage_owner",
            "comments.creator",
            "comments.creation_time",
            "history",
        ]
        params = {
            "include_fields": fields,
            "keywords": "intermittent-failure",
            "keywords_type": "nowords",
            "email2": "wptsync@mozilla.bugs",
            "emailreporter2": "1",
            "emailtype2": "notequals",
            "resolution": "---",
            "f1": "creation_ts",
            "o1": "greaterthan",
            "v1": f"-{self.oldest_bug_days}d",
            "f21": "bug_type",
            "o21": "equals",
            "v21": "defect",
            "f22": "flagtypes.name",
            "o22": "notequals",
            "v22": "needinfo?",
            "f23": "bug_severity",
            "o23": "anyexact",
            "v23": "--, n/a",
            "f24": "keywords",
            "o24": "anyexact",
            "v24": "triaged",
        }
        self.date = lmdutils.get_date_ymd(date)

        return params


if __name__ == "__main__":
    TriagedNoSeverity().run()
