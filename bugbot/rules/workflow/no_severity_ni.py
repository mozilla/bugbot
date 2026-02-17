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
    normal_changes_max = 100

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
            "f1": "bug_type",
            "o1": "equals",
            "v1": "defect",
            "f2": "flagtypes.name",
            "o2": "notsubstring",
            "v2": "needinfo?",
            "f3": "bug_severity",
            "o3": "anyexact",
            "v3": "--, n/a",
            "n6": 1,
            "f6": "product",
            "o6": "changedafter",
            "v6": lookup,
            "n7": 1,
            "f7": "component",
            "o7": "changedafter",
            "v7": lookup,
            "f8": "creation_ts",
            "o8": "lessthaneq",
            "v8": lookup,
            # TODO: Remove when it is not needed anymore
            "f9": "days_elapsed",
            "o9": "lessthaneq",
            "v9": 14 * (datetime.today() - datetime(2025, 10, 1)).days / 7,
        }

        self.date = lmdutils.get_date_ymd(date)

        return params


if __name__ == "__main__":
    NoSeverityNeedInfo().run()
