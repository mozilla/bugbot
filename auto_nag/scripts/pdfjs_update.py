# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import collections
import re

from libmozdata.bugzilla import Bugzilla

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner

PDFJS_UPDATES_METABUG = 1626408
BUG_PATTERN = re.compile(r"[\t ]*Bug[\t ]*([0-9]+)", re.IGNORECASE)


class PDFJSUpdate(BzCleaner):
    def __init__(self):
        super(PDFJSUpdate, self).__init__()
        self.autofix_blocks = {}

    def description(self):
        return "Set PDF.js update bugs as blocking bugs fixed by them"

    def handle_bug(self, bug, data):
        data[str(bug["id"])] = {
            "id": bug["id"],
            "blocks": bug["blocks"],
        }
        return bug

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)
        return {
            "include_fields": ["id", "blocks"],
            "f1": "blocked",
            "o1": "anyexact",
            "v1": PDFJS_UPDATES_METABUG,
            "f2": "creation_ts",
            "o2": "greaterthan",
            "v2": start_date,
            "n3": 1,
            "f3": "blocked",
            "o3": "changedby",
            "v3": utils.get_config("common", "bot_bz_mail")[0],
        }

    def set_autofix(self, bugs):
        blocked_bugs = collections.defaultdict(set)

        def comment_handler(bug, bug_id):
            first_comment = bug["comments"][0]["text"]
            for m in BUG_PATTERN.finditer(first_comment):
                blocked_bugs[bug_id].add(m.group(1))

        Bugzilla(
            bugids=self.get_list_bugs(bugs),
            commenthandler=comment_handler,
            comment_include_fields=["text"],
        ).get_data().wait()

        for bug_id, bug in bugs.items():
            if blocked_bugs[bug_id] <= set(bug["blocks"]):
                continue

            self.autofix_blocks[bug_id] = list(
                blocked_bugs[bug_id] - set(bug["blocks"])
            )

        return bugs

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(PDFJSUpdate, self).get_bugs(date=date, bug_ids=bug_ids)
        self.set_autofix(bugs)

        return bugs

    def get_autofix_change(self):
        cc = self.get_config("cc")
        return {
            bug_id: {
                "cc": {"add": cc},
                "blocks": {"add": blocks},
            }
            for bug_id, blocks in self.autofix_blocks.items()
        }


if __name__ == "__main__":
    PDFJSUpdate().run()
