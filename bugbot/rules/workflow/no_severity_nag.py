# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


import numpy
from libmozdata import utils as lmdutils

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.escalation import Escalation
from bugbot.nag_me import Nag
from bugbot.round_robin import RoundRobin


class NoSeverityNag(BzCleaner, Nag):
    def __init__(self, inactivity_days: int = 4):
        """Constructor

        Args:
            inactivity_days: number of days that a bug should be inactive before
                being considered.
        """
        super(NoSeverityNag, self).__init__()
        self.lookup = utils.get_config(self.name(), "weeks-lookup", 4)
        self.escalation = Escalation(
            self.people,
            data=utils.get_config(self.name(), "escalation"),
            skiplist=utils.get_config("workflow", "supervisor_skiplist", []),
        )
        self.round_robin = RoundRobin.get_instance()
        self.components_skiplist = utils.get_config("workflow", "components_skiplist")
        self.activity_date = str(
            numpy.busday_offset(lmdutils.get_date("today"), -inactivity_days)
        )

    def description(self):
        return "Bugs without a severity or statuses set"

    def nag_template(self):
        return self.template()

    def nag_preamble(self):
        return """<p>
  <ul>
    <li><a href="https://firefox-source-docs.mozilla.org/bug-mgmt/policies/triage-bugzilla.html#why-triage">Why triage?</a></li>
    <li><a href="https://firefox-source-docs.mozilla.org/bug-mgmt/policies/triage-bugzilla.html#what-do-you-triage">What do you triage?</a></li>
    <li><a href="https://firefox-source-docs.mozilla.org/bug-mgmt/guides/priority.html">Priority definitions</a></li>
    <li><a href="https://firefox-source-docs.mozilla.org/bug-mgmt/guides/severity.html">Severity definitions</a></li>
  </ul>
</p>"""

    def get_extra_for_template(self):
        return {"nweeks": self.lookup}

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def has_product_component(self):
        return True

    def ignore_meta(self):
        return True

    def columns(self):
        return ["product", "component", "id", "summary"]

    def handle_bug(self, bug, data):
        if (
            # check if the product::component is in the list
            utils.check_product_component(self.components_skiplist, bug)
            or utils.get_last_no_bot_comment_date(bug) > self.activity_date
        ):
            return None
        return bug

    def get_mail_to_auto_ni(self, bug):
        return None

    def set_people_to_nag(self, bug, buginfo):
        priority = "default"
        if not self.filter_bug(priority):
            return None

        owners = self.round_robin.get(bug, self.date, only_one=False, has_nick=False)
        real_owner = bug["triage_owner"]
        self.add_triage_owner(owners, real_owner=real_owner)
        if not self.add(owners, buginfo, priority=priority):
            self.add_no_manager(buginfo["id"])
        return bug

    def get_bz_params(self, date):
        fields = [
            "triage_owner",
            "flags",
            "comments.creator",
            "comments.creation_time",
        ]
        lookup = f"-{self.lookup * 7}d"

        params = {
            "include_fields": fields,
            "keywords": "intermittent-failure",
            "keywords_type": "nowords",
            "email2": "wptsync@mozilla.bugs",
            "emailreporter2": "1",
            "emailtype2": "notequals",
            "resolution": "---",
            "f31": "bug_type",
            "o31": "equals",
            "v31": "defect",
            "f32": "flagtypes.name",
            "o32": "notsubstring",
            "v32": "needinfo?",
            "f33": "bug_severity",
            "o33": "anyexact",
            "v33": "--, n/a",
            "j2": "OR",
            "f2": "OP",
            "j3": "AND",
            "f3": "OP",
            "f4": "product",
            "o4": "changedbefore",
            "v4": lookup,
            "n5": 1,
            "f5": "product",
            "o5": "changedafter",
            "v5": lookup,
            "n6": 1,
            "f6": "component",
            "o6": "changedafter",
            "v6": lookup,
            "f7": "CP",
            "j8": "AND",
            "f8": "OP",
            "f9": "component",
            "o9": "changedbefore",
            "v9": lookup,
            "n10": 1,
            "f10": "product",
            "o10": "changedafter",
            "v10": lookup,
            "n11": 1,
            "f11": "component",
            "o11": "changedafter",
            "v11": lookup,
            "f12": "CP",
            "j13": "AND",
            "f13": "OP",
            "f14": "creation_ts",
            "o14": "lessthaneq",
            "v14": lookup,
            "n15": 1,
            "f15": "product",
            "o15": "everchanged",
            "n16": 1,
            "f16": "component",
            "o16": "everchanged",
            "f17": "CP",
            "f18": "CP",
            "n20": 1,
            "j20": "OR",
            "f20": "OP",
            "f21": "bug_severity",
            "o21": "changedfrom",
            "v21": "critical",
            "f22": "bug_severity",
            "o22": "changedfrom",
            "v22": "major",
            "f23": "bug_severity",
            "o23": "changedfrom",
            "v23": "blocker",
            "f30": "CP",
        }

        self.date = lmdutils.get_date_ymd(date)

        return params


if __name__ == "__main__":
    NoSeverityNag().run()
