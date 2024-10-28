# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class SecurityApprovalTracking(BzCleaner):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        if not self.init_versions():
            return

        self.version = self.versions[channel] if self.versions else None

        self.extra_ni = None

    def description(self):
        return "Bugs with attachments pending security approval and incomplete tracking flags"

    def handle_bug(self, bug, data):
        # Assuming these bugs are bugs that do not have a status flag set to either "affected" or "unaffected"
        bugid = str(bug["id"])
        data[bugid] = {
            "id": bugid,
            "summary": bug["summary"],
            "assignee": bug["assigned_to"],
        }
        self.add_auto_ni(
            bugid,
            {"mail": bug["assigned_to"], "nickname": bug["assigned_to_detail"]["nick"]},
        )

        return bug

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)

        Bugzilla(
            bugs.keys(),
            include_fields=self.fields,
            bughandler=self.handle_bug,
            bugdata=bugs,
        ).wait()

        self.extra_ni = bugs
        return bugs

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "assignee"]

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        self.status = utils.get_flag(self.version, "status", self.channel)
        self.tracking = utils.get_flag(self.version, "tracking", self.channel)
        self.fields = [
            "id",
            "assigned_to",
            "nickname",
            "flags",
            self.tracking,
            self.status,
        ]

        params = {
            "include_fields": self.fields,
            "resolution": "---",
            "f1": "creation_ts",
            "o1": "greaterthan",
            "v1": start_date,
            "f2": self.status,
            "o2": "anywords",
            "n2": "1",
            "v2": ",".join(["unaffected", "affected"]),
            "f3": "flagtypes.name",
            "o3": "substring",
            "v3": "sec-approval?",
        }

        return params


if __name__ == "__main__":
    SecurityApprovalTracking("beta").run()
    SecurityApprovalTracking("central").run()
    SecurityApprovalTracking("esr").run()
