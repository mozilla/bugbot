# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.hgmozilla import Mercurial

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


def get_csets_from_pushlog(log):
    csets = []
    for push in log["pushes"].values():
        for cset in push["changesets"]:
            if any(cset["node"][:12] in c["desc"] for c in push["changesets"]):
                # if a changeset is mentioned in another in the same central
                # push, assume it's a backout, and ignore it
                continue
            bugs = utils.get_bugs_from_desc(cset["desc"])
            if not bugs:
                continue
            csets.append((cset["node"], bugs[0]))
    return csets


class MissedLandingComment(BzCleaner):
    def __init__(self):
        super().__init__()
        self.bugs = []
        self.repourl = Mercurial.get_repo_url("nightly")

    def description(self):
        return "Changesets in mozilla-central without a bugzilla comment"

    def get_bz_params(self, date):
        start, end = self.get_dates(date)
        log = utils.get_pushlog(start, end)
        # get a list of (changeset, bugid) from the mozilla-central pushlog
        csets = get_csets_from_pushlog(log)

        self.bugs = {}
        for cset, bug in csets:
            self.bugs.setdefault(str(bug), []).append(cset)

        params = {
            "include_fields": ["id", "comments"],
            "bug_id_type": "anyexact",
            "bug_id": ",".join(self.bugs),
        }
        return params

    def filter_no_nag_keyword(self):
        return False

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        assert bugid in self.bugs
        for cset in self.bugs[bugid]:
            short = cset[:12]
            cseturl = "%s/rev/%s" % (self.repourl, short)
            if any(cseturl in comment["text"] for comment in bug["comments"]):
                continue
            if bugid not in data:
                data[bugid] = {"id": bugid, "missing_csets": []}
            data[bugid]["missing_csets"].append((cset, cseturl))

    def columns(self):
        return ["id", "missing_csets"]


if __name__ == "__main__":
    MissedLandingComment().run()
