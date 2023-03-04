# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class MovedToPerformance(BzCleaner):
    """Add a comment to bugs that recently moved to the performance component"""

    def description(self):
        return "Bugs that recently moved to the performance component"

    def get_mail_to_auto_ni(self, bug):
        return {"mail": bug["creator"], "nickname": bug["creator_detail"]["nick"]}

    def get_bz_params(self, date):
        fields = [
            "creator",
        ]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "bug_type": "defect",
            "f1": "product",
            "o1": "equals",
            "v1": "Core",
            "f2": "component",
            "o2": "equals",
            "v2": "Performance",
            "f3": "component",
            "o3": "changedafter",
            "v3": "-7d",
            "n4": 1,
            "f4": "component",
            "o4": "changedafter",
            "v4": "-1d",
            "n6": 1,
            "f6": "longdesc",
            "o6": "casesubstring",
            "v5": "could you make sure the following information is on this bug?",
        }

        return params


if __name__ == "__main__":
    MovedToPerformance().run()
