# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class SecurityUnhideDups(BzCleaner):
    """Security bugs that could be un-hidden"""

    def description(self):
        return "Security bugs that are marked as duplicates of already-public bugs"

    def filter_no_nag_keyword(self):
        return False

    def get_summary(self, bug):
        # This will prevent the default behavior of hiding the summary of
        # security bugs.
        return bug["summary"]

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = bug

        return bug

    def get_bz_params(self, date):
        params = {
            "include_fields": ["dupe_of"],
            "resolution": "DUPLICATE",
            "f1": "bug_group",
            "o1": "substring",
            "v1": "core-security",
        }

        return params

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)

        # Filter out bugs that are not marked as duplicates of open security bugs
        public_sec_bugs = set()

        def bug_handler(bug):
            if (
                bug["resolution"] != "---"
                and not bug["groups"]
                and any(keyword.startswith("sec-") for keyword in bug["keywords"])
            ):
                public_sec_bugs.add(bug["id"])

        bugs_to_query = {bug["dupe_of"] for bug in bugs.values()}
        Bugzilla(
            bugs_to_query,
            include_fields=["id", "resolution", "keywords", "groups"],
            bughandler=bug_handler,
        ).wait()

        bugs = {
            bug_id: bug
            for bug_id, bug in bugs.items()
            if bug["dupe_of"] in public_sec_bugs
        }

        self.query_url = utils.get_bz_search_url({"bug_id": ",".join(bugs.keys())})

        return bugs


if __name__ == "__main__":
    SecurityUnhideDups().run()
