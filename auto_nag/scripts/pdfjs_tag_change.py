# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import re
from collections import Counter

from auto_nag.bzcleaner import BzCleaner

TAG_PATTERN = re.compile(r"(\[pdfjs[^\]]*\])")


class PdfJsTagChange(BzCleaner):
    def __init__(self):
        super(PdfJsTagChange, self).__init__()
        with open("extra/pdfjs_tags.json", "r") as In:
            self.map = json.load(In)
        self.autofix_whiteboard = {}
        self.stats = Counter()

    def description(self):
        return "Change pdfjs tags"

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        whiteboard = bug["whiteboard"]

        def repl(m):
            old = m.group(1)[1:-1]
            new = self.map.get(old, old)
            if new:
                self.stats[new] += 1
            return f"[{new}]" if new else ""

        new_whiteboard = re.sub(TAG_PATTERN, repl, whiteboard)
        if new_whiteboard == whiteboard:
            return None

        self.autofix_whiteboard[bugid] = {
            "whiteboard": new_whiteboard,
        }

        return None

    def get_bz_params(self, date):
        params = {
            "include_fields": ["whiteboard"],
            "resolution": "---",
            "f1": "product",
            "o1": "equals",
            "v1": "Firefox",
            "f2": "component",
            "o2": "equals",
            "v2": "PDF Viewer",
            "f3": "status_whiteboard",
            "o3": "casesubstring",
            "v3": "pdfjs",
        }

        return params

    def get_autofix_change(self):
        return self.autofix_whiteboard

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(PdfJsTagChange, self).get_bugs(date=date, bug_ids=bug_ids)
        # with open("pdfjs_tags_stats.csv", "w") as Out:
        #     for key, val in self.stats.items():
        #         Out.write(f"{key}, {val}\n")

        return bugs


if __name__ == "__main__":
    PdfJsTagChange().run()
