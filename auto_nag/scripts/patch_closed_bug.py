# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner

COMMENT_BODY = "A patch has been attached on this bug, which was already closed. Filing a separate bug will ensure better tracking. If this was not by mistake and further action is needed, please alert the appropriate party."


class PatchClosedBug(BzCleaner):
    def __init__(self):
        super(PatchClosedBug, self).__init__()
        self.days_count = self.get_config("days_count", 5)

    def description(self):
        return "Bugs with recent patches after being closed"

    def columns(self):
        return ["id", "summary", "resolved_at", "latest_patch_at"]

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "resolved_at": bug["cf_last_resolved"],
        }
        return bug

    def has_attachments(self):
        return True

    def attachmenthandler(self, attachments, bugid, data):
        latest_patch = max(
            [
                attachment["last_change_time"]
                for attachment in attachments
                if attachment["content_type"] == "text/x-phabricator-request"
            ]
        )

        bug = data[bugid]
        bug_resolved_at = bug["resolved_at"]
        if latest_patch > bug_resolved_at:
            bug["resolved_at"] = utils.get_human_lag(bug_resolved_at)
            bug["latest_patch_at"] = utils.get_human_lag(latest_patch)
        else:
            del data[bugid]

    def get_attachment_include_fields(self):
        return ["content_type", "last_change_time"]

    def get_bz_params(self, date):
        fields = ["cf_last_resolved"]
        params = {
            "include_fields": fields,
            "bug_status": ["RESOLVED", "VERIFIED"],
            "f1": "bug_status",
            "o1": "changedafter",
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

    def get_bz_search_url(self, params):
        return None

    def get_autofix_change(self):
        return {
            "comment": {"body": COMMENT_BODY},
        }


if __name__ == "__main__":
    PatchClosedBug().run()
