# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class AffectedFlagConfirm(BzCleaner):
    def description(self):
        return "Unconfirmed bugs that have an affected Firefox version flag"

    def get_bz_params(self, date):
        params = {
            "bug_status": "UNCONFIRMED",
            "j1": "OR",
            "f1": "OP",
        }

        statuses = ",".join(
            [
                "affected",
                "wontfix",
                "fix-optional",
                "fixed",
                "disabled",
                "verified",
                "verified disabled",
            ]
        )

        last_version = utils.get_nightly_version_from_bz()
        first_version = last_version - 40
        for version in range(first_version, last_version + 1):
            i = version - first_version + 2
            params[f"f{i}"] = f"cf_status_firefox{version}"
            params[f"o{i}"] = "anyexact"
            params[f"v{i}"] = statuses
        params[f"f{i+1}"] = "CP"

        return params

    def get_autofix_change(self):
        return {
            "comment": {
                "body": "The bug has a release status flag that shows some version of Firefox is affected, thus it will be considered confirmed."
            },
            "status": "NEW",
        }


if __name__ == "__main__":
    AffectedFlagConfirm().run()
