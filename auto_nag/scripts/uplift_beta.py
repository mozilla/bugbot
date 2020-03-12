# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

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
        self.extra_ni = {}

    def description(self):
        return "Bugs fixed in nightly but still affecting beta"

    def has_assignee(self):
        return True

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

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

        bugs_without_regr = {}
        for bugid, info in bugs.items():
            regs = set(info["regression"])
            regs = regs - fixed_bugs
            if not regs:
                bugs_without_regr[bugid] = info

        return bugs_without_regr

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
            # Changed before 2 days ago and not changed after 2 days ago
            # So we get bugs where the last status_central change (fixed or verified)
            # was 2 days ago
            "f3": self.status_central,
            "o3": "changedbefore",
            "v3": f"-{to_wait}d",
            "n4": 1,
            "f4": self.status_central,
            "o4": "changedafter",
            "v4": f"-{to_wait}d",
            #
            "f5": "flagtypes.name",
            "o5": "notsubstring",
            "v5": "approval-mozilla-beta",
            "f6": "flagtypes.name",
            "o6": "notsubstring",
            "v6": "needinfo",
            # Don't nag several times
            "n7": 1,
            "f7": "longdesc",
            "o7": "casesubstring",
            # this a part of the comment we've in templates/uplift_beta_needinfo.txt
            "v7": ", is this bug important enough to require an uplift?",
            # Check if have at least one attachment which is a Phabricator request
            "f8": "attachments.mimetype",
            "o8": "anywordssubstr",
            "v8": "text/x-phabricator-request",
        }

        return params

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(UpliftBeta, self).get_bugs(date=date, bug_ids=bug_ids)
        bugs = self.filter_by_regr(bugs)

        for bugid, data in bugs.items():
            if data["mail"] and data["nickname"]:
                self.extra_ni[bugid] = {"regression": len(data["regressions"])}
                self.add_auto_ni(
                    bugid, {"mail": data["mail"], "nickname": data["nickname"]}
                )

        return bugs


if __name__ == "__main__":
    UpliftBeta().run()
