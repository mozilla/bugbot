# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import timedelta

from dateutil import parser
from libmozdata import utils as lmdutils

from bugbot import utils
from bugbot.bzcleaner import BzCleaner

# Content types Bugzilla uses for patch attachments (Phabricator revisions and
# the legacy Review Board requests).
PATCH_CONTENT_TYPES = ("text/x-phabricator-request", "text/x-review-board-request")

# This exact sentence is posted verbatim in every needinfo comment (injected
# into the template via `get_extra_for_needinfo_template`) AND used as the
# re-nag guard in `get_bz_params` (a bug whose comments already contain it is
# skipped). Both uses reference this single constant so they can never drift
# out of sync; changing the wording keeps the guard correct automatically.
NEEDINFO_QUESTION = (
    "Which branches (beta, release, and/or ESR) are affected by this flaw?"
)

# Products that don't ship on ESR, so their ESR status flags are never set and
# must not be treated as a "missing" flag worth nagging about.
NON_ESR_PRODUCTS = {"Firefox for Android"}


class SecurityAffectedVersions(BzCleaner):
    def __init__(self, days_count: int = 7):
        """Constructor

        Args:
            days_count: only consider bugs that had a patch attached within this
                many days, so we nudge shortly after a patch appears rather than
                on the whole historical backlog.
        """
        super().__init__()
        self.days_count = days_count
        self.start_date = lmdutils.get_date_ymd("today") - timedelta(days=days_count)
        if not self.init_versions():
            return

        # ESR status flags, tracked separately so we can ignore them for
        # products that don't ship on ESR. `esr` and `esr_previous` collapse to
        # the same flag outside an ESR overlap period.
        self.esr_flags = list(
            dict.fromkeys(
                [
                    utils.get_flag(self.versions["esr"], "status", "esr"),
                    utils.get_flag(self.versions["esr_previous"], "status", "esr"),
                ]
            )
        )

        # Release status flags for every branch we care about. De-duplicated to
        # avoid emitting a redundant query clause when ESR flags coincide.
        self.status_flags = list(
            dict.fromkeys(
                [
                    utils.get_flag(self.versions["central"], "status", "nightly"),
                    utils.get_flag(self.versions["beta"], "status", "beta"),
                    utils.get_flag(self.versions["release"], "status", "release"),
                    *self.esr_flags,
                ]
            )
        )

    def description(self):
        return "Security bugs with an attached patch but a missing release status flag"

    def has_needinfo(self):
        return True

    def get_mail_to_auto_ni(self, bug):
        for field in ["assigned_to", "triage_owner"]:
            person = bug.get(field, "")
            if person and not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None

    def get_extra_for_needinfo_template(self):
        return {"question": NEEDINFO_QUESTION}

    def columns(self):
        return ["id", "summary"]

    def _has_recent_patch(self, bug):
        """Whether the bug has a non-obsolete patch attached within the window.

        The query matches bugs that have a patch-typed attachment, but it can
        not tell whether that attachment is obsolete or old, so we double-check
        here.
        """
        return any(
            not attachment["is_obsolete"]
            and attachment["content_type"] in PATCH_CONTENT_TYPES
            and parser.parse(attachment["creation_time"]) >= self.start_date
            for attachment in bug.get("attachments", [])
        )

    def _relevant_flags(self, bug):
        """The status flags that matter for this bug's product.

        Products that don't ship on ESR (e.g. Firefox for Android) never get
        their ESR flags set, so those flags must not count as "missing".
        """
        if bug["product"] in NON_ESR_PRODUCTS:
            return [flag for flag in self.status_flags if flag not in self.esr_flags]
        return self.status_flags

    def handle_bug(self, bug, data):
        if not self._has_recent_patch(bug):
            return None

        # The query's OR group matches if *any* flag is empty, but for products
        # without ESR that would fire on the always-empty ESR flag alone. Re-check
        # that at least one *relevant* flag is actually missing.
        if all(bug.get(flag, "---") != "---" for flag in self._relevant_flags(bug)):
            return None

        return bug

    def get_email_data(self, date):
        # This rule only acts on Bugzilla (posting needinfos); it does not send
        # a summary report to release managers. Run the normal pipeline so the
        # needinfos are applied, then return no data so `send_email` skips the
        # email. (The `.html` template is still used by the framework's
        # "too many changes" abort alert, so it must stay.)
        super().get_email_data(date)
        return []

    def get_bz_params(self, date):
        params = {
            "include_fields": [
                "assigned_to",
                "triage_owner",
                "product",
                "attachments.content_type",
                "attachments.is_obsolete",
                "attachments.creation_time",
                *self.status_flags,
            ],
            # Only open bugs: we want to prompt while setting the flags is still
            # actionable (i.e. the patch is in review, not yet landed).
            "resolution": "---",
            # Coarse recency filter: the bug changed within the window. Since
            # attaching a patch bumps `delta_ts`, this is a superset of "a patch
            # was attached within the window"; the precise per-attachment date
            # check happens in `_has_recent_patch`.
            "f1": "delta_ts",
            "o1": "greaterthan",
            "v1": f"-{self.days_count}d",
            # The bug is hidden in a core-security group (e.g. core-security,
            # firefox-core-security, core-security-release). This intentionally
            # excludes non-core security groups (e.g. cloud-services-security),
            # matching the scope of the "which branches are affected" question.
            "f2": "bug_group",
            "o2": "substring",
            "v2": "core-security",
            # The bug has at least one Phabricator patch attachment.
            "f3": "attachments.mimetype",
            "o3": "equals",
            "v3": "text/x-phabricator-request",
            # Don't nag twice: skip bugs where we already asked.
            "n4": 1,
            "f4": "longdesc",
            "o4": "casesubstring",
            "v4": NEEDINFO_QUESTION,
            # At least one relevant release status flag is still empty (unset).
            "f5": "OP",
            "j5": "OR",
        }

        i = 6
        for flag in self.status_flags:
            params[f"f{i}"] = flag
            params[f"o{i}"] = "equals"
            params[f"v{i}"] = "---"
            i += 1

        params[f"f{i}"] = "CP"

        return params


if __name__ == "__main__":
    SecurityAffectedVersions().run()
