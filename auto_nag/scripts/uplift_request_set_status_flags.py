# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class UpliftRequestSetStatusFlags(BzCleaner):
    def __init__(self, channel):
        super().__init__()
        if not self.init_versions():
            return

        self.channel = channel
        self.bug_ids = []

        self.version = self.versions[self.channel]
        if self.channel == "esr":
            self.bug_ids = utils.get_report_bugs(self.channel + self.version)
        else:
            self.bug_ids = utils.get_report_bugs(self.channel)

        self.status_changes = {}

    def description(self):
        return "Set release status flags based on uplift request"

    def get_bz_params(self, date):
        status = utils.get_flag(self.version, "status", self.channel)
        return {
            "include_fields": ["_custom"],
            "bug_id": ",".join(self.bug_ids),
            "f1": status,
            "o1": "anywordssubstr",
            "v1": ",".join(["---", "unaffected", "?", "wontfix", "disabled"]),
        }

    def handle_bug(self, bug, data):
        data[str(bug["id"])] = bug

    def get_status_changes(self, bugs):
        for bug_id in bugs.keys():
            v = int(self.version)
            flag = utils.get_flag(v, "status", self.channel)

            self.status_changes[bug_id] = {
                "comment": self.description(),
                flag: "affected",
            }

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        self.get_status_changes(bugs)
        return bugs

    def get_autofix_change(self):
        return self.status_changes

    def get_extra_for_template(self):
        return {
            "channel": "nightly" if self.channel == "central" else self.channel,
            "version": self.version,
        }

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def columns(self):
        return ["id", "summary"]


if __name__ == "__main__":
    UpliftRequestSetStatusFlags("beta").run()
    UpliftRequestSetStatusFlags("release").run()
    UpliftRequestSetStatusFlags("esr").run()
