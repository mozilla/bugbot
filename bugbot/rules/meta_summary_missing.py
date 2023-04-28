# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.bzcleaner import BzCleaner


class MetaSummaryMissing(BzCleaner):
    no_bugmail = True

    def __init__(self):
        super(MetaSummaryMissing, self).__init__()
        self.autofix_meta = {}

    def description(self):
        return "Bugs with the meta keyword but not [meta] in the title"

    def get_autofix_change(self):
        return self.autofix_meta

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        summary = bug["summary"]
        self.autofix_meta[bugid] = {"summary": "[meta] " + summary}
        return bug

    def get_bz_params(self, date):
        days_lookup = self.get_config("days_lookup", default=180)
        fields = ["summary"]
        return {
            "include_fields": fields,
            "resolution": ["---", "FIXED"],
            "keywords": "meta",
            "keywords_type": "allwords",
            "short_desc": r"(\[meta\]|\[tracking\])",
            "short_desc_type": "notregexp",
            "f1": "days_elapsed",
            "o1": "lessthan",
            "v1": days_lookup,
        }


if __name__ == "__main__":
    MetaSummaryMissing().run()
