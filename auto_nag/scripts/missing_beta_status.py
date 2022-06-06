# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class MissingBetaStatus(BzCleaner):
    def __init__(self):
        super(MissingBetaStatus, self).__init__()
        self.autofix_status = {}
        if not self.init_versions():
            return

        self.status_nightly = utils.get_flag(
            self.versions["central"], "status", "nightly"
        )
        self.status_beta = utils.get_flag(self.versions["beta"], "status", "beta")
        self.status_release = utils.get_flag(
            self.versions["release"], "status", "release"
        )

    def description(self):
        return "Bugs with a missing beta status flag"

    def ignore_date(self):
        return True

    def get_autofix_change(self):
        return self.autofix_status

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        nightly = bug[self.status_nightly]
        release = bug[self.status_release]
        doc = self.get_documentation()

        # If the two status are different, we don't know what to set.
        # If this affects nightly and release, beta will likely be affected too.
        # Otherwise we cannot say for sure if beta should be the same as nightly
        # and release, and we better be conservative in this case to avoid bugs
        # falling through the cracks.
        if nightly == release:
            if release in ["affected", "?"]:
                self.autofix_status[bugid] = {
                    "comment": {
                        "body": "Change the status for beta to have the same as nightly and release.\n{}".format(
                            doc
                        )
                    },
                    self.status_beta: nightly,
                }
            else:
                self.autofix_status[bugid] = {
                    "comment": {
                        "body": f"Since it has been ${nightly} for nightly and release, is it ${nightly} for beta too?\n${doc}"
                    },
                    self.status_beta: "?",
                }
        else:
            self.autofix_status[bugid] = {
                "comment": {
                    "body": "Since the status are different for nightly and release, what's the status for beta?\n{}".format(
                        doc
                    )
                },
                self.status_beta: "?",
            }
        return bug

    def get_bz_params(self, date):
        fields = [self.status_nightly, self.status_release]
        params = {
            "include_fields": fields,
            "f1": self.status_beta,
            "o1": "equals",
            "v1": "---",
            "f2": self.status_release,
            "o2": "notequals",
            "v2": "---",
            "f3": self.status_nightly,
            "o3": "notequals",
            "v3": "---",
        }

        return params


if __name__ == "__main__":
    MissingBetaStatus().run()
