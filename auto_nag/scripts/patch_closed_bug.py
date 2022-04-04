# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime, timedelta

import pytz
from dateutil import parser

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner

COMMENT_BODY = "A patch has been attached on this bug, which was already closed. Filing a separate bug will ensure better tracking. If this was not by mistake and further action is needed, please alert the appropriate party."


class PatchClosedBug(BzCleaner):
    def __init__(self):
        super(PatchClosedBug, self).__init__()
        self.days_count = self.get_config("days_count", 2)
        today = pytz.utc.localize(datetime.utcnow())
        self.start_date = today - timedelta(self.days_count)

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
            "latest_patch_at": utils.get_human_lag(latest_patch_at),
        }
        return bug

    def get_bz_params(self, date):
        fields = [
            "cf_last_resolved",
            "attachments.creation_time",
            "attachments.content_type",
            "attachments.is_obsolete",
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
            "v6": COMMENT_BODY,
        }

        return params

    def get_autofix_change(self):
        return {
            "comment": {"body": COMMENT_BODY},
        }


if __name__ == "__main__":
    PatchClosedBug().run()
