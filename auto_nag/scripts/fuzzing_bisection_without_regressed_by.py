# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner

MAX_DEPTH = 2


class FuzzingBisectionWithoutRegressedBy(BzCleaner):
    def description(self):
        return "Bugs with a fuzzing bisection and without regressed_by"

    def get_max_ni(self):
        return utils.get_config(self.name(), "max_ni")

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "is_meta": "meta" in bug["keywords"],
            "assigned_to_email": bug["assigned_to"],
            "assigned_to_nickname": bug["assigned_to_detail"]["nick"],
            "depends_on": bug["depends_on"],
        }
        return bug

    def set_autofix(self, bugs):
        for bugid, info in bugs.items():
            self.add_auto_ni(
                bugid,
                {
                    "mail": info["assigned_to_email"],
                    "nickname": info["assigned_to_nickname"],
                },
            )

    def _get_bz_params(self, blocked_ids):
        return {
            "include_fields": ["assigned_to", "depends_on", "keywords"],
            "f1": "blocked",
            "o1": "anyexact",
            "v1": ",".join(str(bid) for bid in blocked_ids),
            "f2": "regressed_by",
            "o2": "isempty",
            "n3": 1,
            "f3": "regressed_by",
            "o3": "everchanged",
            "n4": 1,
            "f4": "longdesc",
            "o4": "casesubstring",
            "v4": "since this bug contains a bisection range, could you fill (if possible) the regressed_by field",
        }

    def get_bz_params(self, date):
        return self._get_bz_params([316898])

    def get_recursive_blocking(self, bugs, got_bugs, depth=0):
        meta_bugs = (bug for bug in bugs.values() if bug["is_meta"])

        blocked_ids = list(
            {
                bug_id
                for bug in meta_bugs
                for bug_id in bug["depends_on"]
                if bug_id not in got_bugs
            }
        )
        if len(blocked_ids) == 0:
            return

        got_bugs.update(blocked_ids)

        if depth == MAX_DEPTH:
            return

        chunks = (
            blocked_ids[i : (i + Bugzilla.BUGZILLA_CHUNK_SIZE)]
            for i in range(0, len(blocked_ids), Bugzilla.BUGZILLA_CHUNK_SIZE)
        )

        for chunk in chunks:
            params = self._get_bz_params(chunk)
            self.amend_bzparams(params, None)
            Bugzilla(
                params,
                bughandler=self.bughandler,
                bugdata=bugs,
            ).get_data().wait()

        self.get_recursive_blocking(bugs, got_bugs, depth + 1)

    def filter_bugs(self, bugs):
        # Exclude meta bugs.
        bugs = {bug["id"]: bug for bug in bugs.values() if not bug["is_meta"]}

        # Exclude bugs assigned to nobody.
        bugs = {
            bug["id"]: bug
            for bug in bugs.values()
            if not utils.is_no_assignee(bug["assigned_to_email"])
        }

        # Exclude bugs that do not have a range found by BugMon.
        def comment_handler(bug, bug_id):
            if not any(
                "BugMon: Reduced build range" in comment["text"]
                or "The bug appears to have been introduced in the following build range"
                in comment["text"]
                for comment in bug["comments"]
            ):
                del bugs[bug_id]

        Bugzilla(
            bugids=self.get_list_bugs(bugs),
            commenthandler=comment_handler,
            comment_include_fields=["text"],
        ).get_data().wait()

        return bugs

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(FuzzingBisectionWithoutRegressedBy, self).get_bugs(
            date=date, bug_ids=bug_ids
        )
        self.get_recursive_blocking(bugs, set(bugs))
        bugs = self.filter_bugs(bugs)
        self.set_autofix(bugs)

        return bugs


if __name__ == "__main__":
    FuzzingBisectionWithoutRegressedBy().run()
