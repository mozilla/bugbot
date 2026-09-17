# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla

from bugbot import utils
from bugbot.bzcleaner import BzCleaner

# This phrase is posted in every needinfo comment (injected into the template
# via `get_extra_for_needinfo_template`) AND used as the re-nag guard in
# `get_bz_params`. Both uses reference this single constant so they can never
# drift out of sync.
COMMENT_MARKER = "please make an uplift decision for"

# The marker used by the previous wording. Bugzilla comments are immutable, so
# bugs nagged before the rewording carry only this one: keep filtering on it
# too, otherwise they would all be nagged a second time.
LEGACY_COMMENT_MARKER = ", is this bug important enough to require an uplift?"

# `fix-optional` means release management would take a fix but won't chase it,
# so it deserves the same question as `affected`.
AFFECTED_STATUSES = ["affected", "fix-optional"]


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
        self.approval_beta = utils.get_flag(self.beta, "approval", "beta")

        # The needinfo mentions ESR generically, so the current ESR's flags are
        # enough to tell whether an ESR uplift is still to be decided.
        self.esr = self.versions["esr"]
        self.status_esr = utils.get_flag(self.esr, "status", "esr")
        self.approval_esr = utils.get_flag(self.esr, "approval", "esr")

        # Bugs will be added to `extra_ni` later after being fetched
        self.extra_ni = {
            "status_beta": f"status-firefox{self.beta}",
            "question": COMMENT_MARKER,
        }

    def description(self):
        return "Bugs fixed in nightly but still affecting beta or ESR"

    def has_assignee(self):
        return True

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "channels", "summary", "assignee"]

    def get_channels_to_uplift(self, bug):
        """Get the channels the patch still needs an uplift decision for.

        A channel qualifies when it is affected and nobody has asked for
        approval on it yet. The query only guarantees that one of them is
        affected, so this is also where the ESR-only case (beta wontfix, ESR
        still affected) gets picked up.
        """
        requested_approvals = {
            flag["name"]
            for attachment in bug["attachments"]
            for flag in attachment["flags"]
        }

        channels = []
        if (
            bug.get(self.status_beta) in AFFECTED_STATUSES
            and self.approval_beta not in requested_approvals
        ):
            channels.append("beta")
        if (
            bug.get(self.status_esr) in AFFECTED_STATUSES
            and self.approval_esr not in requested_approvals
        ):
            channels.append("ESR")

        return channels

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

        channels = self.get_channels_to_uplift(bug)
        if not channels:
            return None

        data[bugid] = {
            "id": bugid,
            "mail": assignee,
            "nickname": nickname,
            "summary": self.get_summary(bug),
            "regressions": bug["regressions"],
            "channels": channels,
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
            "regressions",
            "attachments.creation_time",
            "attachments.is_obsolete",
            "attachments.content_type",
            "attachments.flags",
            "cf_last_resolved",
            "assigned_to",
            "flags",
            self.status_beta,
            self.status_esr,
        ]
        params = {
            "include_fields": fields,
            "bug_type": "defect",
            "resolution": ["---", "FIXED"],
            "f1": self.status_central,
            "o1": "anyexact",
            "v1": ",".join(["fixed", "verified"]),
            # Don't nag several times
            "n2": 1,
            "f2": "longdesc",
            "o2": "casesubstring",
            "v2": COMMENT_MARKER,
            # Same, for bugs nagged with the previous wording
            "n3": 1,
            "f3": "longdesc",
            "o3": "casesubstring",
            "v3": LEGACY_COMMENT_MARKER,
            # Check if have at least one attachment which is a Phabricator request
            "f4": "attachments.mimetype",
            "o4": "anyexact",
            "v4": ["text/x-phabricator-request", "text/x-github-pull-request"],
            # skip if whiteboard contains checkin-needed-beta (e.g. test-only uplift)
            "f5": "status_whiteboard",
            "o5": "notsubstring",
            "v5": "[checkin-needed-beta]",
            # Beta or ESR must be affected. Which of them still needs a
            # decision is worked out in get_channels_to_uplift(), where we can
            # look at the approval requests channel by channel.
            "j6": "OR",
            "f6": "OP",
            "f7": self.status_beta,
            "o7": "anyexact",
            "v7": AFFECTED_STATUSES,
            "f8": self.status_esr,
            "o8": "anyexact",
            "v8": AFFECTED_STATUSES,
            "f9": "CP",
        }

        return params

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(UpliftBeta, self).get_bugs(date=date, bug_ids=bug_ids)
        bugs = self.filter_by_regr(bugs)

        for bugid, data in bugs.items():
            if data["mail"] and data["nickname"]:
                self.extra_ni[bugid] = {
                    "regression": len(data["regressions"]),
                    "channels": data["channels"],
                }
                self.add_auto_ni(
                    bugid, {"mail": data["mail"], "nickname": data["nickname"]}
                )

        return bugs


if __name__ == "__main__":
    UpliftBeta().run()
