# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class MismatchPriorityTracking(BzCleaner):
    def __init__(self, channel: str, target_priority: str):
        assert target_priority in ("P1", "P2")

        super().__init__()
        self.init_versions()
        self.channel = channel
        self.target_priority = target_priority

    def description(self):
        return f"Bug tracked for {self.channel} with a bad priority (P3, P4 or P5)"

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        version = self.versions[self.channel]
        params = {
            "resolution": [
                "---",
                "FIXED",
                "INVALID",
                "WONTFIX",
                "DUPLICATE",
                "WORKSFORME",
                "INCOMPLETE",
                "SUPPORT",
                "EXPIRED",
                "MOVED",
            ],
            "f1": utils.get_flag(version, "tracking", self.channel),
            "o1": "anyexact",
            "v1": ["+", "blocking"],
            "f2": utils.get_flag(version, "status", self.channel),
            "o2": "anyexact",
            "v2": ["---", "affected"],
        }
        return params

    def get_autofix_change(self):
        return {
            "comment": {
                "body": f"Changing the priority to `{self.target_priority}` as the bug is tracked by a release manager for the current `{self.channel}`.\nSee [Triage for Bugzilla](https://firefox-source-docs.mozilla.org/bug-mgmt/policies/triage-bugzilla.html#automatic-bug-updates) for more information.\nIf you disagree, please discuss with a release manager."
            },
            "priority": self.target_priority,
        }


if __name__ == "__main__":
    MismatchPriorityTracking("release", "P1").run()
    MismatchPriorityTracking("beta", "P1").run()
    MismatchPriorityTracking("esr", "P1").run()
    MismatchPriorityTracking("nightly", "P2").run()
