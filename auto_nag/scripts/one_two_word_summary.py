# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class OneTwoWordSummary(BzCleaner):
    def __init__(self):
        super(OneTwoWordSummary, self).__init__()

    def description(self):
        return "Bugs with only one or two words in the summary"

    def get_bz_params(self, date):
        days_lookup = self.get_config("days_lookup", default=7)
        skiplist = self.get_config("regex_skiplist", [])

        params = {
            "bug_type": "defect",
            "resolution": "---",
            "f1": "days_elapsed",
            "o1": "lessthan",
            "v1": days_lookup,
            "f2": "short_desc",
            "o2": "regexp",
            "v2": "^([a-zA-Z0-9_]+ [a-zA-Z0-9_]+|[a-zA-Z0-9_]+)$",
        }

        if skiplist:
            for i, regex in enumerate(skiplist):
                j = str(i + 3)
                params["f" + j] = "short_desc"
                params["o" + j] = "notregexp"
                params["v" + j] = regex

        return params


if __name__ == "__main__":
    OneTwoWordSummary().run()
