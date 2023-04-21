# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class Intermittents(BzCleaner):
    normal_changes_max: int = 300

    def description(self):
        return "Intermittent test failure bugs unchanged in 21 days"

    def get_bz_params(self, date):
        params = {
            "include_fields": ["_custom"],
            "n1": "1",
            "f1": "longdescs.count",
            "o1": "changedafter",
            "v1": "-3w",
            "f2": "blocked",
            "o2": "isempty",
            "f3": "flagtypes.name",
            "o3": "notequals",
            "v3": "needinfo?",
            "f4": "OP",
            "n4": "1",
            "f5": "bug_status",
            "o5": "changedto",
            "v5": "REOPENED",
            "f6": "bug_status",
            "o6": "changedafter",
            "v6": "-7d",
            "f7": "CP",
            "f8": "bug_severity",
            "o8": "notequals",
            "v8": ["S1", "critical"],
            "n9": "1",
            "f9": "component",
            "o9": "anyexact",
            "v9": ["New Tab Page", "Messaging System"],
            "f10": "keywords",
            "o10": "allwords",
            "v10": "intermittent-failure",
            "f11": "keywords",
            "o11": "nowords",
            "v11": "leave-open, test-verify-fail",
            "priority": ["P3", "P5"],
            "resolution": "---",
            "status_whiteboard_type": "notregexp",
            "status_whiteboard": "(leave open|leave-open|leaveopen|test disabled|test-disabled|testdisabled)",
        }

        return params

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        status_flags = {
            field: "wontfix"
            for field, value in bug.items()
            if field.startswith("cf_status_") and value in ("affected", "fix-optional")
        }

        self.autofix_changes[bugid] = {
            **status_flags,
            "status": "RESOLVED",
            "resolution": "INCOMPLETE",
            "comment": {
                "body": f"https://wiki.mozilla.org/Bug_Triage#Intermittent_Test_Failure_Cleanup\n{self.get_documentation()}"
            },
        }

        return bug


if __name__ == "__main__":
    Intermittents().run()
