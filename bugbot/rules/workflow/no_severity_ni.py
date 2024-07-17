# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime

import numpy
from libmozdata import utils as lmdutils

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.round_robin import RoundRobin


class NoSeverityNeedInfo(BzCleaner):
    def __init__(self, inactivity_days: int = 4):
        """Constructor

        Args:
            inactivity_days: number of days that a bug should be inactive before
                being considered.
        """
        super(NoSeverityNeedInfo, self).__init__()
        self.lookup_first = utils.get_config(self.name(), "weeks_lookup", 2)
        self.round_robin = RoundRobin.get_instance()
        self.components_skiplist = utils.get_config("workflow", "components_skiplist")
        self.activity_date = str(
            numpy.busday_offset(lmdutils.get_date("today"), -inactivity_days)
        )

    def description(self):
        return "Bugs without a severity or statuses set"

    def has_product_component(self):
        return True

    def ignore_meta(self):
        return True

    def columns(self):
        return ["product", "component", "id", "summary"]

    def handle_bug(self, bug, data):
        if (
            # Check if the product::component is in the list
            utils.check_product_component(self.components_skiplist, bug)
            or utils.get_last_no_bot_comment_date(bug) > self.activity_date
        ):
            return None
        return bug

    def get_mail_to_auto_ni(self, bug):
        string_to_search = "The severity field is not set for this bug."

        for comment in bug.get("comments", []):
            if string_to_search in comment.get("raw_text", ""):
                return None

        mail, nick = self.round_robin.get(bug, self.date)
        if mail and nick:
            return {"mail": mail, "nickname": nick}
        return None

    def get_bz_params(self, date):
        fields = [
            "triage_owner",
            "flags",
            "comments.creator",
            "comments.creation_time",
            "comments.raw_text",
        ]
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
        }
        self.date = lmdutils.get_date_ymd(date)
        first = f"-{self.lookup_first * 7}d"
        params.update(
            {
                "f2": "flagtypes.name",
                "o2": "notequals",
                "v2": "needinfo?",
                "j3": "OR",
                "f3": "OP",
                "j4": "AND",
                "f4": "OP",
                "n5": 1,  # Ensure no change after the first period
                "f5": "product",
                "o5": "changedafter",
                "v5": first,
                "f6": "product",  # The bug has changed
                "o6": "changedafter",
                "v6": self.lookup_first * 7,
                "n7": 1,
                "f7": "component",
                "o7": "changedafter",
                "v7": first,
                "f8": "CP",
                "j9": "AND",
                "f9": "OP",
                "n10": 1,
                "f10": "component",
                "o10": "changedafter",
                "v10": first,
                "f11": "component",
                "o11": "changedafter",
                "v11": self.lookup_first * 7,
                "n12": 1,
                "f12": "product",
                "o12": "changedafter",
                "v12": first,
                "f13": "CP",
                "j14": "AND",
                "f14": "OP",
                "f15": "creation_ts",
                "o15": "lessthaneq",
                "v15": first,
                "f16": "creation_ts",
                "o16": "greaterthan",
                "v16": self.lookup_first * 7,
                "n17": 1,
                "f17": "product",
                "o17": "everchanged",
                "n18": 1,
                "f18": "component",
                "o18": "everchanged",
                "f19": "CP",
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
                "f24": "CP",
                "f30": "CP",
            }
        )

        # TODO: the following code can be removed in 2024.
        # https://github.com/mozilla/bugbot/issues/1596
        # Almost 500 old bugs have no severity set. The intent of the following
        # is to have them triaged in batches where every week we include more
        # bugs. Once the list of old bugs are reduced, we could safely remove
        # the following code.
        passed_time = datetime.now() - datetime.fromisoformat("2023-06-09")
        oldest_bug_months = 56 + passed_time.days
        n = utils.get_last_field_num(params)
        params.update(
            {
                f"f{n}": "creation_ts",
                f"o{n}": "greaterthan",
                f"v{n}": f"-{oldest_bug_months}m",
            }
        )

        return params


if __name__ == "__main__":
    NoSeverityNeedInfo().run()
