# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime

from libmozdata import utils as lmdutils

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.escalation import Escalation
from auto_nag.nag_me import Nag
from auto_nag.round_robin import RoundRobin


class NoSeverity(BzCleaner, Nag):
    def __init__(self, typ, inactivity_days: int = 3):
        """Constructor

        Args:
            typ: the mode that the tool should run with (first or second). Nag
                emails will be sent only if `typ` is second.
            inactivity_days: number of days that a bug should be inactive before
                being considered.
        """
        super(NoSeverity, self).__init__()
        assert typ in {"first", "second"}
        self.typ = typ
        self.lookup_first = utils.get_config(self.name(), "first-step", 2)
        self.lookup_second = utils.get_config(self.name(), "second-step", 4)
        self.escalation = Escalation(
            self.people,
            data=utils.get_config(self.name(), "escalation-{}".format(typ)),
            skiplist=utils.get_config("workflow", "supervisor_skiplist", []),
        )
        self.round_robin = RoundRobin.get_instance()
        self.components_skiplist = utils.get_config("workflow", "components_skiplist")
        self.activity_date = lmdutils.get_date("today", inactivity_days)

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
    <li><a href="https://firefox-source-docs.mozilla.org/bug-mgmt/guides/severity.html">Severty definitions</a></li>
  </ul>
</p>"""

    def get_extra_for_template(self):
        return {
            "nweeks": self.lookup_first if self.typ == "first" else self.lookup_second
        }

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def has_product_component(self):
        return True

    def ignore_meta(self):
        return True

    def columns(self):
        return ["component", "id", "summary"]

    def handle_bug(self, bug, data):
        if (
            # check if the product::component is in the list
            utils.check_product_component(self.components_skiplist, bug)
            or utils.get_last_no_bot_comment_date(bug) > self.activity_date
        ):
            return None
        return bug

    def get_mail_to_auto_ni(self, bug):
        if self.typ == "second":
            return None

        mail, nick = self.round_robin.get(bug, self.date)
        if mail and nick:
            return {"mail": mail, "nickname": nick}

        return None

    def set_people_to_nag(self, bug, buginfo):
        priority = "default"
        if not self.filter_bug(priority):
            return None

        # don't nag in the first step (just a ni is enough)
        if self.typ == "first":
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
            "flags",
            "comments.creator",
            "comments.creation_time",
        ]
        params = {
            "include_fields": fields,
            "keywords": "intermittent-failure",
            "keywords_type": "nowords",
            "email2": "wptsync@mozilla.bugs",
            "emailreporter2": "1",
            "emailtype2": "notequals",
            "resolution": "---",
            "f21": "bug_type",
            "o21": "equals",
            "v21": "defect",
            "f22": "flagtypes.name",
            "o22": "notsubstring",
            "v22": "needinfo?",
            "f23": "bug_severity",
            "o23": "anyexact",
            "v23": "--, n/a",
        }
        self.date = lmdutils.get_date_ymd(date)
        first = f"-{self.lookup_first * 7}d"
        second = f"-{self.lookup_second * 7}d"
        if self.typ == "first":
            # TODO: change this when https://bugzilla.mozilla.org/1543984 will be fixed
            # Here we have to get bugs where product/component have been set (bug has been triaged)
            # between 4 and 2 weeks
            # If the product/component never changed after bug creation, we need to get them too
            # (second < p < first && c < first) ||
            # (second < c < first && p < first) ||
            # ((second < creation < first) && pc never changed)
            params.update(
                {
                    "f2": "flagtypes.name",
                    "o2": "notequals",
                    "v2": "needinfo?",
                    "j3": "OR",
                    "f3": "OP",
                    "j4": "AND",
                    "f4": "OP",
                    "n5": 1,  # we use a negation here to be sure that no change after first
                    "f5": "product",
                    "o5": "changedafter",
                    "v5": first,
                    "f6": "product",  # here the bug has changed
                    "o6": "changedafter",
                    "v6": second,
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
                    "v11": second,
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
                    "v16": second,
                    "n17": 1,
                    "f17": "product",
                    "o17": "everchanged",
                    "n18": 1,
                    "f18": "component",
                    "o18": "everchanged",
                    "f19": "CP",
                    "f20": "CP",
                }
            )
        else:
            params.update(
                {
                    "j2": "OR",
                    "f2": "OP",
                    "j3": "AND",
                    "f3": "OP",
                    "f4": "product",
                    "o4": "changedbefore",
                    "v4": second,
                    "n5": 1,
                    "f5": "product",
                    "o5": "changedafter",
                    "v5": second,
                    "f6": "CP",
                    "j7": "AND",
                    "f7": "OP",
                    "f8": "component",
                    "o8": "changedbefore",
                    "v8": second,
                    "n9": 1,
                    "f9": "component",
                    "o9": "changedafter",
                    "v9": second,
                    "f10": "CP",
                    "j11": "AND",
                    "f11": "OP",
                    "f12": "creation_ts",
                    "o12": "lessthaneq",
                    "v12": second,
                    "n13": 1,
                    "f13": "product",
                    "o13": "everchanged",
                    "n14": 1,
                    "f14": "component",
                    "o14": "everchanged",
                    "f15": "CP",
                    "f16": "CP",
                }
            )

        # TODO: the following code can be removed in 2023.
        # https://github.com/mozilla/relman-auto-nag/issues/1592#issuecomment-1201893220
        # Almost 500 old bugs has no severity set. The intent of the following
        # is to have them triaged in patches where every week we include more
        # bugs. Once the list of old bugs are reduced, we could safely remove
        # the following code.
        passed_time = datetime.now() - datetime.fromisoformat("2022-08-01")
        oldest_bug_months = 12 + (passed_time.days // 7)
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
    NoSeverity("first").run()
    NoSeverity("second").run()
