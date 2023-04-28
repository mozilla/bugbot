# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.bzcleaner import BzCleaner


class CrashSignatureConfirm(BzCleaner):
    def description(self):
        return "Unconfirmed bugs that have a crash signature"

    def get_bz_params(self, date):
        params = {
            "bug_status": "UNCONFIRMED",
            "f1": "cf_crash_signature",
            "o1": "isnotempty",
        }

        return params

    def get_autofix_change(self):
        return {
            "comment": {
                "body": "The bug has a crash signature, thus the bug will be considered confirmed."
            },
            "status": "NEW",
        }


if __name__ == "__main__":
    CrashSignatureConfirm().run()
