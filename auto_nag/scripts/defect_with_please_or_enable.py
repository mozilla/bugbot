# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class DefectWithPlease(BzCleaner):
    def __init__(self):
        super(DefectWithPlease, self).__init__()

    def description(self):
        return "Defect with description starting with 'Please', 'Enable' or 'Disable'"

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        days_lookup = self.get_config("days_lookup")
        params = {
            "resolution": "---",
            "short_desc": r"^(please|enable|disable)",
            "short_desc_type": "regexp",
            "bug_type": ["defect"],
            "f1": "days_elapsed",
            "o1": "lessthan",
            "v1": days_lookup,
        }
        return params


if __name__ == "__main__":
    DefectWithPlease().run()
