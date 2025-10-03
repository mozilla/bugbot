# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime

import numpy
from libmozdata import utils as lmdutils

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.escalation import Escalation
from bugbot.nag_me import Nag
from bugbot.round_robin import RoundRobin


class NoSeverityNeedInfo(BzCleaner, Nag):
    def __init__(self, inactivity_days: int = 4):
        """Constructor

        Args:
            inactivity_days: number of days that a bug should be inactive before
                being considered.
        """
        super(NoSeverityNeedInfo, self).__init__()
        self.lookup = utils.get_config(self.name(), "weeks_lookup", 2)
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
        mail, nick = self.round_robin.get(bug, self.date)
        if mail and nick:
            return {"mail": mail, "nickname": nick}

        return None

    def set_people_to_nag(self, bug, buginfo):
        priority = "default"
        if not self.filter_bug(priority):
            return None

        return bug

    def get_bz_params(self, date):
        fields = [
            "triage_owner",
            "flags",
            "comments.creator",
            "comments.creation_time",
        ]
        lookup = f"-{self.lookup * 7}d"

        # Find bugs that have been filed since `lookup` weeks, or whose component or product have been set since `lookup` weeks
        params = {
            "include_fields": fields,
            "keywords": "intermittent-failure",
            "keywords_type": "nowords",
            "email2": "wptsync@mozilla.bugs",
            "emailreporter2": "1",
            "emailtype2": "notequals",
            "resolution": "---",
            "f15": "bug_type",
            "o15": "equals",
            "v15": "defect",
            "f16": "flagtypes.name",
            "o16": "notsubstring",
            "v16": "needinfo?",
            "f17": "bug_severity",
            "o17": "anyexact",
            "v17": "--, n/a",
            # TODO: Remove when it is not needed anymore
            "f18": "days_elapsed",
            "o18": "lessthaneq",
            "v18": 14 * (datetime.today() - datetime(2025, 10, 1)).days / 7,
            "f2": "flagtypes.name",
            "o2": "notequals",
            "v2": "needinfo?",
            "j3": "OR",
            "f3": "OP",
            "j4": "AND",
            "f4": "OP",
            "n5": 1,
            "f5": "product",
            "o5": "changedafter",
            "v5": lookup,
            "n6": 1,
            "f6": "component",
            "o6": "changedafter",
            "v6": lookup,
            "f7": "creation_ts",
            "o7": "lessthaneq",
            "v7": lookup,
            "f8": "CP",
            "j9": "OR",
            "f9": "OP",
            "f10": "bug_severity",
            "o10": "changedfrom",
            "v10": "critical",
            "f11": "bug_severity",
            "o11": "changedfrom",
            "v11": "major",
            "f12": "bug_severity",
            "o12": "changedfrom",
            "v12": "blocker",
            "f13": "CP",
            "f14": "CP",
        }

        self.date = lmdutils.get_date_ymd(date)

        return params


if __name__ == "__main__":
    NoSeverityNeedInfo().run()
