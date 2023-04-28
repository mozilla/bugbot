# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class GoodFirstBugUnassignInactive(BzCleaner):
    def __init__(self):
        super(GoodFirstBugUnassignInactive, self).__init__()
        self.nmonths = utils.get_config(self.name(), "months_lookup")
        self.autofix_assignee = {}

    def description(self):
        return "Bugs with good-first-bug keyword and no activity for the last {} months".format(
            self.nmonths
        )

    def get_autofix_change(self):
        return self.autofix_assignee

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        doc = self.get_documentation()

        self.autofix_assignee[bugid] = {
            "comment": {
                "body": "This good-first-bug hasn't had any activity for {} months, it is automatically unassigned.\n{}".format(
                    self.nmonths, doc
                )
            },
            "reset_assigned_to": True,
            "status": "NEW",
        }

        return bug

    def get_bz_params(self, date):
        fields = ["assigned_to"]
        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "keywords",
            "o1": "casesubstring",
            "v1": "good-first-bug",
            "f2": "days_elapsed",
            "o2": "greaterthan",
            "v2": self.nmonths * 30,
        }
        utils.get_empty_assignees(params, True)

        return params


if __name__ == "__main__":
    GoodFirstBugUnassignInactive().run()
