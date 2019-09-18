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
            "email1":	["intermittent-bug-filer@mozilla.bugs"],
            "emailreporter1":	["1"],
            "emailtype1":	["exact"],
            "f1":	["longdescs.count"],
            "f2":	["blocked"],
            "f3":	["flagtypes.name"],
            "f4":	["OP"],
            "f5":	["bug_status"],
            "f6":	["bug_status"],
            "f7":	["CP"],
            "f8":	["bug_severity"],
            "f9":	["component"],
            "keywords":	["leave-open"],
            "keywords_type":	["nowords"],
            "n1":	["1"],
            "n4":	["1"],
            "o1":	["changedafter"],
            "o2":	["isempty"],
            "o3":	["notequals"],
            "o5":	["changedto"],
            "o6":	["changedafter"],
            "o8":	["notequals"],
            "o9":	["nowordssubstr"],
            "priority":	["P5"],
            "resolution":	["---"],
            "status_whiteboard":	["(leave open|leave-open|leaveopen|test disabled|test-disabled|testdisabled)"],
            "status_whiteboard_type":	["notregexp"],
            "v1":	["-3w"],
            "v3":	["needinfo?"],
            "v5":	["REOPENED"],
            "v6":	["-7d"],
            "v8":	["critical"],
            "v9":	["new tab page, messaging system"],
        }

        return params

    def get_autofix_change(self):
        return {
            "status": {"add": ["RESOLVED"]},
            "resolution": {"add": ["INCOMPLETE"]},
            "comment": {
                "body": f"https://wiki.mozilla.org/Bug_Triage#Intermittent_Test_Failure_Cleanup\n{self.get_documentation()}"
            },
        }



if __name__ == "__main__":
    Intermittents().run()
