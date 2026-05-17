# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import timedelta

from libmozdata import utils as lmdutils
from libmozdata.socorro import SuperSearch

from bugbot import utils
from bugbot.bzcleaner import BzCleaner

# Marker phrase placed in the needinfo comment so subsequent runs can detect
# that this rule has already actioned a bug and skip it via the longdesc
# substring filter in get_bz_params(). Keep it stable across template edits.
COMMENT_MARKER = "crashes are still being reported against this signature"


class CrashesAfterFix(BzCleaner):
    """Crash bugs whose signature is still crashing on Nightly some days
    after the fix landed. Need-infos the assignee to ask whether the fix was
    incomplete or whether a follow-up is needed."""

    def __init__(self):
        super().__init__()
        self.min_days_since_fix = utils.get_config(self.name(), "min_days_since_fix", 4)
        self.max_days_since_fix = utils.get_config(
            self.name(), "max_days_since_fix", 10
        )
        self.min_crash_count = utils.get_config(self.name(), "min_crash_count", 5)
        self.extra_ni = {}
        # bug_id (str) -> per-bug context used to query Socorro and fill the
        # needinfo template (see bughandler()).
        self.bug_data = {}

    def description(self):
        return (
            "Bugs whose crash signatures keep crashing on Nightly "
            "{}-{} days after the fix landed"
        ).format(self.min_days_since_fix, self.max_days_since_fix)

    def has_assignee(self):
        return True

    def get_extra_for_template(self):
        return {
            "min_days": self.min_days_since_fix,
            "max_days": self.max_days_since_fix,
            "min_crashes": self.min_crash_count,
        }

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def get_bz_params(self, date):
        today = lmdutils.get_date_ymd(date)
        # cf_last_resolved must fall in the window
        #   [today - max_days, today - min_days]
        # so the fix has been on Nightly for at least min_days but not more
        # than max_days. Bugzilla compares cf_last_resolved against a date
        # string with greaterthan/lessthan.
        oldest_fix = lmdutils.get_date_str(
            today - timedelta(days=self.max_days_since_fix)
        )
        newest_fix = lmdutils.get_date_str(
            today - timedelta(days=self.min_days_since_fix)
        )

        fields = [
            "id",
            "summary",
            "assigned_to",
            "assigned_to_detail",
            "cf_crash_signature",
            "cf_last_resolved",
            "cf_status_firefox_nightly",
        ]

        params = {
            "include_fields": fields,
            "resolution": "FIXED",
            "bug_status": ["RESOLVED", "VERIFIED"],
            # Has a non-empty crash signature.
            "f1": "cf_crash_signature",
            "o1": "isnotempty",
            # The fix is in Nightly.
            "f2": "cf_status_firefox_nightly",
            "o2": "equals",
            "v2": "fixed",
            # cf_last_resolved > today - max_days (recent enough).
            "f3": "cf_last_resolved",
            "o3": "greaterthan",
            "v3": oldest_fix,
            # cf_last_resolved < today - min_days (old enough to be in nightly
            # builds for the monitoring window).
            "f4": "cf_last_resolved",
            "o4": "lessthan",
            "v4": newest_fix,
            # Skip bugs that already have an open needinfo so we don't pile on.
            "f5": "flagtypes.name",
            "o5": "notsubstring",
            "v5": "needinfo?",
            # Skip bugs where we've already left a needinfo comment for this
            # rule (idempotency across daily runs).
            "n6": 1,
            "f6": "longdesc",
            "o6": "casesubstring",
            "v6": COMMENT_MARKER,
        }

        return params

    def bughandler(self, bug, data):
        if not bug.get("cf_crash_signature"):
            return

        sigs = sorted(utils.get_signatures(bug["cf_crash_signature"]))
        if not sigs:
            return

        assignee = bug.get("assigned_to") or ""
        if utils.is_no_assignee(assignee):
            return

        nickname = ""
        if bug.get("assigned_to_detail"):
            nickname = bug["assigned_to_detail"].get("nick", "")

        fix_date = bug.get("cf_last_resolved")
        if not fix_date:
            return

        bug_id = str(bug["id"])
        self.bug_data[bug_id] = {
            "summary": self.get_summary(bug),
            "signatures": sigs,
            "fix_date": fix_date,
            "assignee_email": assignee,
            "assignee_nickname": nickname,
        }

    def _query_socorro(self, info):
        """Faceted SuperSearch over Nightly crashes since the day after the fix
        landed. Returns (total_count, per_signature_counts, since_date_str)."""
        fix_dt = lmdutils.get_date_ymd(info["fix_date"])
        since = lmdutils.get_date_str(fix_dt + timedelta(days=1))

        counts = {}

        def handler(json, data):
            if json.get("errors"):
                return
            for facet in json.get("facets", {}).get("signature", []):
                data[facet["term"]] = int(facet["count"])

        params = {
            "product": "Firefox",
            "release_channel": "nightly",
            "date": ">=" + since,
            "signature": ["=" + s for s in info["signatures"]],
            "_results_number": 0,
            "_facets": "signature",
            "_facets_size": max(len(info["signatures"]), 1),
        }

        SuperSearch(params=params, handler=handler, handlerdata=counts).wait()
        return sum(counts.values()), counts, since

    def get_bugs(self, date="today", bug_ids=[]):
        super().get_bugs(date=date, bug_ids=bug_ids)

        result = {}
        for bug_id, info in self.bug_data.items():
            total, per_sig, since = self._query_socorro(info)
            if total < self.min_crash_count:
                continue

            self.extra_ni[bug_id] = {
                "crash_count": total,
                "since": since,
                "fix_date": info["fix_date"][:10],
                "signatures": info["signatures"],
                "per_signature_counts": per_sig,
            }
            self.add_auto_ni(
                bug_id,
                {
                    "mail": info["assignee_email"],
                    "nickname": info["assignee_nickname"],
                },
            )
            result[bug_id] = {"id": bug_id, "summary": info["summary"]}

        return result


if __name__ == "__main__":
    CrashesAfterFix().run()
