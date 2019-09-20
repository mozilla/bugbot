# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class Intermittents(BzCleaner):
    def __init__(self):
        super(Intermittents, self).__init__()

    def description(self):
        return "Intermittent test failure bugs unchanged in 21 days"

    def get_bz_params(self, date):
        params = {
            "email1": "intermittent-bug-filer@mozilla.bugs",
            "emailreporter1": "1",
            "emailtype1": "exact",
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
            "v8": "critical",
            "f9": "component",
            "o9": "nowordssubstr",
            "v9": "new tab page, messaging system",
            "keywords_type": "nowords",
            "keywords": "leave-open",
            "priority": "P5",
            "resolution": "---",
            "status_whiteboard_type": "notregexp",
            "status_whiteboard": "(leave open|leave-open|leaveopen|test disabled|test-disabled|testdisabled)",
        }

        return params

    def get_autofix_change(self):
        return {
            "status": {"add": "RESOLVED"},
            "resolution": {"add": "INCOMPLETE"},
            "comment": {
                "body": f"https://wiki.mozilla.org/Bug_Triage#Intermittent_Test_Failure_Cleanup\n{self.get_documentation()}"
            },
        }


if __name__ == "__main__":
    Intermittents().run()
