# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import dateutil.parser
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class UpliftBeta(BzCleaner):
    def __init__(self):
        super(UpliftBeta, self).__init__()
        if not self.init_versions():
            return

        self.beta = self.versions["beta"]
        self.status_central = utils.get_flag(
            self.versions["central"], "status", "central"
        )
        self.status_beta = utils.get_flag(self.beta, "status", "beta")

    def description(self):
        return "Bugs fixed in nightly but still affect other supported channels"

    def has_assignee(self):
        return True

    def columns(self):
        return ["id", "summary", "assignee"]

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        assignee = bug.get("assigned_to", "")
        if utils.is_no_assignee(assignee):
            assignee = ""
            nickname = ""
        else:
            nickname = bug["assigned_to_detail"]["nick"]

        data[bugid] = {
            "id": bugid,
            "mail": assignee,
            "nickname": nickname,
            "summary": self.get_summary(bug),
            "regressions": bug["regressions"],
        }
        return bug

    def filter_bugs(self, bugs):
        # Get the bugs where status_central has been set few days ago

        if not bugs:
            return bugs

        to_wait = self.get_config("days_to_wait")

        def history_handler(bug, data):
            bugid = str(bug["id"])
            last_fixed_date = None
            for h in bug["history"]:
                for change in h["changes"]:
                    if change["field_name"] == self.status_central and change[
                        "added"
                    ] in {"fixed", "verified"}:
                        last_fixed_date = dateutil.parser.parse(h["when"])

            if last_fixed_date and (self.date - last_fixed_date).days >= to_wait:
                data.add(bugid)

        bugids = list(bugs.keys())
        data = set()
        Bugzilla(
            bugids=bugids, historyhandler=history_handler, historydata=data
        ).get_data().wait()

        return {bugid: info for bugid, info in bugs.items() if bugid in data}

    def filter_by_regr(self, bugs):
        # Filter the bugs which don't have any regression or where the regressions are all closed
        def bug_handler(bug, data):
            if bug["status"] in {"RESOLVED", "VERIFIED", "CLOSED"}:
                data.add(bug["id"])

        bugids = {r for info in bugs.values() for r in info["regressions"]}
        if not bugids:
            return bugs

        fixed_bugs = set()
        Bugzilla(
            bugids=list(bugids),
            include_fields=["id", "status"],
            bughandler=bug_handler,
            bugdata=fixed_bugs,
        ).get_data().wait()

        new_bugs = {}
        for bugid, info in bugs.items():
            regs = set(info["regression"])
            regs = regs - fixed_bugs
            if not regs:
                del info["regression"]
                new_bugs[bugid] = info

        return new_bugs

    def get_bz_params(self, date):
        self.date = lmdutils.get_date_ymd(date)
        to_wait = self.get_config("days_to_wait")
        fields = [self.status_beta, "regressions"]
        params = {
            "include_fields": fields,
            "bug_type": "defect",
            "resolution": ["---", "FIXED"],
            "f1": self.status_central,
            "o1": "anyexact",
            "v1": ",".join(["fixed", "verified"]),
            "f2": self.status_beta,
            "o2": "anyexact",
            "v2": "affected",
            "f3": "flagtypes.name",
            "o3": "notsubstring",
            "v3": "approval-mozilla-beta",
            "f4": "flagtypes.name",
            "o4": "notsubstring",
            "v4": "needinfo",
            "f5": "flagtypes.name",
            "o5": "changedbefore",
            "v5": f"-{to_wait}d",
            "n6": 1,
            "f6": "longdesc",
            "o6": "casesubstring",
            "v6": ", is that bug important enough to require an uplift?",
        }

        return params

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(UpliftBeta, self).get_bugs(date=date, bug_ids=bug_ids)
        bugs = self.filter_by_regr(bugs)
        bugs = self.filter_bugs(bugs)

        for bugid, data in bugs.items():
            if data["mail"] and data["nickname"]:
                self.add_auto_ni(
                    bugid, {"mail": data["mail"], "nickname": data["nickname"]}
                )

        return bugs


if __name__ == "__main__":
    UpliftBeta().run()
