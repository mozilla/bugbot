# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from pprint import pprint

class SurveySecurityBugs(BzCleaner):
    LIST_OF_PEOPLE_TO_REACH_OUT = [
        "continuation@gmail.com",  # mccr8
        "jdemooij@mozilla.com",  # jandem (js/jit)
        "nical.bugzilla@gmail.com",  # nical (gfx)
        "emilio@crisal.io",  # emilio (css/style/layout)
    ]

    def __init__(self):
        super(SurveySecurityBugs, self).__init__()
        self.changes_per_bug = {}

    def description(self):
        return "Submit survey to assignee of a security bug"

    def get_bz_params(self, date):
        params = {
            # maybe we need more fields to do our changes (?)
            "include_fields": ["assigned_to", "whiteboard"],
            # find fixed bugs
            "bug_status": "RESOLVED,VERIFIED",
            "resolution": "FIXED",
            # find bugs only in these products
            "f5": "product",
            "o5": "anywordssubstr",
            "v5": "Core,DevTools,Firefox,GeckoView,NSPR,NSS,Toolkit,WebExtensions",
            # bugs changed to RESOLVED in last month
            "chfield": "bug_status",
            "chfieldfrom": "-1m",
            "chfieldto": "NOW",
            "chfieldvalue": "RESOLVED",
            # keywords has either sec-critical or sec-high
            "f1": "keywords",
            "o1": "anywords",
            "v1": "sec-critical,sec-high",
            # whiteboard doesnt have [sec-survey] (to avoid us asking twice)
            "f2": "status_whiteboard",
            "o2": "notsubstring",
            "v2": "[sec-survey]",
            # has at least one attachment (i.e., hopefully a patch)
            "f3": "attachments.count",
            "o3": "greaterthan",
            "v3": "0",
            # assigned to any of those we have agreed to help out
            "f4": "assigned_to",
            "o4": "anywords",
            "v4": ",".join(SurveySecurityBugs.LIST_OF_PEOPLE_TO_REACH_OUT),
        }

        return params

    def handle_bug(self, bug, data):
        assignee = bug["assigned_to"]
        bugid = str(bug["id"])

        new_whiteboard = bug["whiteboard"] + "[sec-survey]"
        self.changes_per_bug[bugid] = {
            "comment": {"body": self.comment_tpl_for_bugid(bugid)},
            "whiteboard": new_whiteboard,
            "flags": [
                {
                "name": "needinfo",
                    "requestee": assignee,
                    "status": "?",
                    "new": "true",
                }
            ],
        }

        return bug

    def get_autofix_change(self):
        return self.changes_per_bug

    def comment_tpl_for_bugid(self, bugid):
        URL = "https://docs.google.com/forms/d/e/1FAIpQLSe9uRXuoMK6tRglbNL5fpXbun_oEb6_xC2zpuE_CKA_GUjrvA/viewform" \
              "?usp=pp_url&entry.2124261401=" + \
              "https%3A%2F%2Fbugzilla.mozilla.org%2Fshow_bug.cgi%3Fid%3D" + bugid

        return "As part of a security bug pattern analysis, we are requesting your help with a high level analysis" + \
               "of this bug. It is our hope to develop static analysis (or potentially runtime/dynamic analysis)" + \
               "in the future to identify classes of bugs.\n\n" + \
               "Please visit [this google form]({}) to reply.""".format(URL)


if __name__ == "__main__":
    SurveySecurityBugs().run()
