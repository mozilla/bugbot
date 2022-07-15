# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime, timedelta

import humanize
import pytz
from dateutil import parser
from libmozdata import utils as lmdutils

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class PatchClosedBug(BzCleaner):
    def __init__(self, days_count: int = 2, wait_time: int = 2):
        """Constructor

        Args:
            days_count: the maximum number of days from the submission date for
                an attachment to be considered.
            wait_time: the number of hours to wait after the attachment
                submission before considering it. This time gap allows people to
                set missed uplift flags, i.e., `approval-mozilla-*`.
        """
        super(PatchClosedBug, self).__init__()

        self.days_count = days_count
        self.start_date = lmdutils.get_date_ymd("today") - timedelta(days_count)
        self.wait_time = pytz.utc.localize(
            datetime.utcnow() - timedelta(hours=wait_time)
        )

    def description(self):
        return "Bugs with recent patches after being closed"

    def columns(self):
        return ["id", "summary", "resolved_at", "latest_patch_at"]

    # Resolving https://github.com/mozilla/relman-auto-nag/issues/1300 should clean this
    # including improve the wording in the template (i.e., "See the search query on Bugzilla").
    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)
        self.query_url = utils.get_bz_search_url({"bug_id": ",".join(bugs.keys())})
        return bugs

    def handle_bug(self, bug, data):
        patches = [
            attachment["creation_time"]
            for attachment in bug["attachments"]
            if attachment["content_type"] == "text/x-phabricator-request"
            and not attachment["is_obsolete"]
            and not any(
                flag["name"].startswith("approval-mozilla-")
                for flag in attachment["flags"]
            )
            and parser.parse(attachment["creation_time"]) < self.wait_time
        ]
        if len(patches) == 0:
            return

        latest_patch_at = parser.parse(max(patches))
        if latest_patch_at < self.start_date:
            return

        resolved_at = parser.parse(bug["cf_last_resolved"])
        if latest_patch_at < resolved_at:
            return

        bugid = str(bug["id"])
        data[bugid] = {
            "resolved_at": utils.get_human_lag(resolved_at),
            "latest_patch_at": f"{humanize.naturaldelta(latest_patch_at - resolved_at)} after resolution",
        }
        return bug

    def get_bz_params(self, date):
        fields = [
            "cf_last_resolved",
            "attachments.creation_time",
            "attachments.content_type",
            "attachments.is_obsolete",
            "attachments.flags",
        ]
        params = {
            "include_fields": fields,
            "bug_status": ["RESOLVED", "VERIFIED"],
            "f1": "delta_ts",
            "o1": "greaterthan",
            "v1": f"-{self.days_count}d",
            "f2": "attachments.mimetype",
            "o2": "equals",
            "v2": "text/x-phabricator-request",
            "n6": 1,
            "f6": "longdesc",
            "o6": "casesubstring",
            "v6": "A patch has been attached on this bug, which was already closed.",
        }

        return params

    def get_autofix_change(self):
        return {
            "comment": {
                "body": "A patch has been attached on this bug, which was already closed. If the patch doesn't change behavior (e.g. landing a test case, or fixing a typo), there's nothing to do. Otherwise, filing a separate bug will ensure better tracking. If this was not by mistake and further action is needed, please alert the appropriate party."
            },
        }


if __name__ == "__main__":
    PatchClosedBug().run()
