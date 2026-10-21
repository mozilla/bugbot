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

# Uplifts are requested from the Lando page of the revision.
LANDO_REVISION_URL = "https://lando.moz.tools/D{}/"

# For low severity bugs, the uplift question isn't worth asking when the
# release is close: their beta status flag is set to `fix-optional` instead of
# needinfoing the assignee, and possibly to `wontfix` once the release is too
# close for an uplift to happen. The values are the number of days to the
# release from which each status is set, `None` meaning at any time; a status
# without an entry is never set. Severities without an entry, like S3 for now,
# always get the question, e.g. `"S3": {"fix-optional": 7, "wontfix": 3}` would
# enable it.
DEFAULT_LOW_SEVERITY_DAYS_TO_RELEASE = {
    "S4": {"fix-optional": 2},
}


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

        self.low_severity_days_to_release = self.get_config(
            "low_severity_days_to_release", DEFAULT_LOW_SEVERITY_DAYS_TO_RELEASE
        )

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

    def get_revisions(self, bug):
        """Get the Phabricator revisions of the non-obsolete patches."""
        return [
            {"id": f"D{rev_id}", "url": LANDO_REVISION_URL.format(rev_id)}
            for rev_id in utils.get_phab_revision_ids(bug)
        ]

    def is_security_bug(self, bug):
        return any("sec" in group for group in bug["groups"]) or any(
            keyword.startswith("sec-") for keyword in bug.get("keywords", [])
        )

    def get_low_severity_status(self, bug):
        """Get the beta status to set for a low severity bug.

        None means that the bug should get the beta uplift question instead.
        Security bugs always get the question: setting their status needs more
        context than their severity.
        """
        if self.is_security_bug(bug):
            return None

        days = self.low_severity_days_to_release.get(bug.get("severity"))
        if days is None:
            return None

        for status in ("wontfix", "fix-optional"):
            if status in days and (
                days[status] is None or self.days_to_release <= days[status]
            ):
                return status

        return None

    def get_low_severity_reason(self, bug, new_status):
        """Get the explanation for setting the beta status of a low severity bug."""
        severity = bug["severity"]
        days = self.low_severity_days_to_release[severity]
        reason = f"Since this is an {severity} bug"
        if days[new_status] is not None:
            reason += f" and the release is {self.days_to_release} days away"
        reason += f", setting `{self.status_beta}` to `{new_status}`: "
        if new_status == "wontfix":
            reason += "the fix will ship with the next release."
        else:
            reason += (
                "an uplift will be considered if requested, but it isn't required."
            )

        return reason

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        channels = self.get_channels_to_uplift(bug)

        # Low severity bugs get a beta status change instead of the beta
        # question. The ESR question is still asked. As beta is only in the
        # channels when nobody asked for a beta uplift, a pending request is
        # never overridden. The change is only applied in get_bugs(), once the
        # bugs with open regressions have been filtered out.
        beta_change = None
        new_status = self.get_low_severity_status(bug)
        if new_status and "beta" in channels:
            channels.remove("beta")
            status = bug[self.status_beta]
            if status != new_status:
                beta_change = {
                    "status": status,
                    "new_status": new_status,
                    "reason": self.get_low_severity_reason(bug, new_status),
                }

        assignee = bug.get("assigned_to", "")
        if utils.is_no_assignee(assignee):
            assignee = ""
            nickname = ""
        else:
            nickname = bug["assigned_to_detail"]["nick"]

        if self.is_needinfo_on_assignee(bug.get("flags", []), assignee):
            channels = []

        if not channels and not beta_change:
            return None

        data[bugid] = {
            "id": bugid,
            "mail": assignee,
            "nickname": nickname,
            "summary": self.get_summary(bug),
            "regressions": bug["regressions"],
            "channels": channels,
            "revisions": self.get_revisions(bug),
            "beta_change": beta_change,
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
        self.days_to_release = (utils.get_next_release_date() - self.date).days
        fields = [
            "regressions",
            "attachments.creation_time",
            "attachments.is_obsolete",
            "attachments.content_type",
            "attachments.file_name",
            "attachments.flags",
            "cf_last_resolved",
            "assigned_to",
            "flags",
            "severity",
            "keywords",
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

        for bugid, data in list(bugs.items()):
            beta_change = data["beta_change"]
            if beta_change:
                self.autofix_changes[bugid] = {
                    self.status_beta: beta_change["new_status"],
                    "comment": {
                        "body": (
                            "The patch landed in nightly and beta is "
                            f"{beta_change['status']}. {beta_change['reason']}"
                            f"\n\n{self.get_documentation()}"
                        )
                    },
                }

            # Bugs only getting a beta status change have no question to ask.
            if not data["channels"]:
                del bugs[bugid]
                continue

            if data["mail"] and data["nickname"]:
                self.extra_ni[bugid] = {
                    "regression": len(data["regressions"]),
                    "channels": data["channels"],
                    "revisions": data["revisions"],
                    "beta_change": data["beta_change"],
                }
                added = self.add_auto_ni(
                    bugid, {"mail": data["mail"], "nickname": data["nickname"]}
                )
                # The needinfo comment explains the beta status change, and a
                # bug can only get one comment.
                if added and data["beta_change"]:
                    del self.autofix_changes[bugid]["comment"]

        return bugs


if __name__ == "__main__":
    UpliftBeta().run()
