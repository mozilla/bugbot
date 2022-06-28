# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class UntriagedWithImportantSev(BzCleaner):
    def description(self):
        return "Bugs in untriaged with an important severity"

    def get_bz_params(self, date):
        return {
            "resolution": ["---"],
            "bug_severity": ["S1", "S2"],
            "component": "Untriaged",
        }


if __name__ == "__main__":
    UntriagedWithImportantSev().run()
