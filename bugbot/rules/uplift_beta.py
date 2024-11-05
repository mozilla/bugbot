# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


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

        # Bugs will be added to `extra_ni` later after being fetched
        self.extra_ni = {"status_beta": f"status-firefox{self.beta}"}

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

        if self.is_needinfo_on_assignee(bug.get("flags", []), assignee):
            return None

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
            regs = set(info["regressions"])
            regs = regs - fixed_bugs
            if not regs:
                bugs_without_regr[bugid] = info

        return bugs_without_regr

    def is_needinfo_on_assignee(self, flags, assignee):
        return any(
            flag["name"] == "needinfo"
            and flag["status"] == "?"
            and flag["requestee"] == assignee
            for flag in flags
        )

    def get_bz_params(self, date):
        self.date = lmdutils.get_date_ymd(date)
        fields = [
            self.status_beta,
            "regressions",
            "attachments.creation_time",
            "attachments.is_obsolete",
            "attachments.content_type",
            "cf_last_resolved",
            "assigned_to",
            "flags",
        ]
        params = {
            "include_fields": fields,
            "bug_type": "defect",
            "resolution": ["---", "FIXED"],
            "f1": self.status_central,
            "o1": "anyexact",
            "v1": ",".join(["fixed", "verified"]),
            "f2": self.status_beta,
            "o2": "anyexact",
            "v2": ["affected", "fix-optional"],
            "f3": "flagtypes.name",
            "o3": "notsubstring",
            "v3": "approval-mozilla-beta",
            # Don't nag several times
            "n5": 1,
            "f5": "longdesc",
            "o5": "casesubstring",
            # this a part of the comment we've in templates/uplift_beta_needinfo.txt
            "v5": ", is this bug important enough to require an uplift?",
            # Check if have at least one attachment which is a Phabricator request
            "f6": "attachments.mimetype",
            "o6": "anyexact",
            "v6": ["text/x-phabricator-request", "text/x-github-pull-request"],
            # skip if whiteboard contains checkin-needed-beta (e.g. test-only uplift)
            "f7": "status_whiteboard",
            "o7": "notsubstring",
            "v7": "[checkin-needed-beta]",
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
