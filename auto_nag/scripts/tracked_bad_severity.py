# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class TrackedBadSeverity(BzCleaner):
    def __init__(self):
        super(TrackedBadSeverity, self).__init__()
        # need to check that versions aren't messy
        if not self.init_versions():
            return

    def description(self):
        return "Bug tracked in a release but with a small severity"

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        # TODO add support for ESR here?
        value = ",".join(["affected", "fixed"])
        params = {
            "bug_severity": ["S3", "normal", "S4", "minor", "trivial", "enhancement"],
            "f1": "OP",
            "j1": "OR",
            "f2": "OP",
            "f3": "cf_tracking_firefox_release",
            "o3": "equals",
            "v3": "blocking",
            "f4": "cf_status_firefox_release",
            "o4": "anyexact",
            "v4": value,
            "f5": "CP",
            "f6": "OP",
            "f7": "cf_tracking_firefox_beta",
            "o7": "equals",
            "v7": "blocking",
            "f8": "cf_status_firefox_beta",
            "o8": "anyexact",
            "v8": value,
            "f9": "CP",
            "f10": "OP",
            "f11": "cf_tracking_firefox_nightly",
            "o11": "equals",
            "v11": "blocking",
            "f12": "cf_status_firefox_nightly",
            "o12": "anyexact",
            "v12": value,
            "f13": "CP",
            "f14": "CP",
        }

        return params

    def get_autofix_change(self):
        return {
            "comment": {
                "body": f"This bug is tracked by a release manager but with a low severity so change it to S2.\n{self.get_documentation()}"
            },
            "severity": "S2",
        }


if __name__ == "__main__":
    TrackedBadSeverity().run()
