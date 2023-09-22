# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class CopyDuplicateInfo(BzCleaner):
    def __init__(self):
        super(CopyDuplicateInfo, self).__init__()
        self.autofix_data = {}

    def description(self):
        return "Bugs which are DUPLICATE and some info haven't been moved"

    def set_autofix(self, bugs, dups, signatures):
        for bugid, missed_sgns in signatures.items():
            sgns = dups[bugid]["signature"]
            sgns = utils.add_signatures(sgns, missed_sgns)
            self.autofix_data[bugid] = {
                "cf_crash_signature": sgns,
                "comment": {"body": "Copying crash signatures from duplicate bugs."},
            }

    def get_autofix_change(self):
        return self.autofix_data

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "id": bugid,
            "summary": self.get_summary(bug),
            "signature": bug.get("cf_crash_signature", ""),
            "dupe": str(bug["dupe_of"]),
            "version": bug["version"],
            "is_private": bool(bug["groups"]),
        }
        return bug

    def get_dups(self, bugs):
        bugids = [info["dupe"] for info in bugs.values()]
        data = {}

        Bugzilla(
            bugids=bugids,
            include_fields=[
                "cf_crash_signature",
                "dupe_of",
                "id",
                "summary",
                "groups",
                "version",
            ],
            bughandler=self.handle_bug,
            bugdata=data,
        ).get_data().wait()

        return data

    def compare(self, bugs, dups):
        # each bug in bugs is the dup of one in dups
        # so the characteristics of this bug should be in the dup
        signatures = {}
        for bugid, info in bugs.items():
            dupid = info["dupe"]
            if dupid not in dups:
                # the bug is unaccessible (sec bug for example)
                continue

            dup = dups[dupid]
            if info["is_private"] and not dup["is_private"]:
                # We avoid copying signatures from private to public bugs
                continue

            bs = utils.get_signatures(info["signature"])
            ds = utils.get_signatures(dup["signature"])
            if not bs.issubset(ds):
                signatures[dupid] = bs - ds

        return signatures

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        fields = ["cf_crash_signature", "dupe_of", "version", "groups"]
        params = {
            "include_fields": fields,
            "resolution": "DUPLICATE",
            "f1": "resolution",
            "o1": "changedafter",
            "v1": start_date,
        }

        return params

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(CopyDuplicateInfo, self).get_bugs(date=date, bug_ids=bug_ids)
        dups = self.get_dups(bugs)
        signatures = self.compare(bugs, dups)

        self.set_autofix(bugs, dups, signatures)

        return {bugid: dups[bugid] for bugid in signatures}


if __name__ == "__main__":
    CopyDuplicateInfo().run()
