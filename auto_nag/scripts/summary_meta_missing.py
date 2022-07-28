# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class MetaSummaryMissing(BzCleaner):
    no_bugmail = True

    def description(self):
        return "Bugs without the meta keyword but with [meta] in the title"

    def get_bz_params(self, date):
        days_lookup = self.get_config("days_lookup", default=180)
        return {
            "resolution": ["---", "FIXED"],
            "keywords": "meta",
            "keywords_type": "nowords",
            "short_desc": r"(\[meta\]|\[tracking\])",
            "short_desc_type": "regexp",
            "f1": "days_elapsed",
            "o1": "lessthan",
            "v1": days_lookup,
        }

    def get_autofix_change(self):
        return {"keywords": {"add": ["meta"]}}


if __name__ == "__main__":
    MetaSummaryMissing().run()
