# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Dict

from libmozdata.connection import Connection
from libmozdata.phabricator import PhabricatorAPI
from tenacity import retry, stop_after_attempt, wait_exponential

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.user_activity import PHAB_CHUNK_SIZE, UserActivity, UserStatus


class InactivePatchAuthor(BzCleaner):
    """Bugs with patches from inactive authors"""

    def __init__(self):
        """Constructor"""
        super(InactivePatchAuthor, self).__init__()
        self.phab = PhabricatorAPI(utils.get_login_info()["phab_api_key"])
        self.user_activity = UserActivity(phab=self.phab)

    def description(self):
        return "Bugs with patches from inactive authors"

    def columns(self):
        return ["id", "summary", "author"]

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)
        rev_ids = {rev_id for bug in bugs.values() for rev_id in bug["rev_ids"]}
        revisions = self._get_revisions_with_inactive_authors(list(rev_ids))

        for bugid, bug in list(bugs.items()):
            inactive_authors = [
                revisions[rev_id] for rev_id in bug["rev_ids"] if rev_id in revisions
            ]
            if inactive_authors:
                bug["authors"] = inactive_authors
                self._unassign_inactive_authors(bugid, inactive_authors)
            else:
                del bugs[bugid]

        self.query_url = utils.get_bz_search_url({"bug_id": ",".join(bugs.keys())})
        return bugs

    def _unassign_inactive_authors(self, bugid: str, inactive_authors: list) -> None:
        comment = "The author of this patch has been inactive. The patch has been unassigned for others to take over."
        for author in inactive_authors:
            self.phab.request(
                "differential.revision.edit",
                {
                    "transactions": [{"type": "authorPHID", "value": None}],
                    "objectIdentifier": author["rev_id"],
                },
            )
            self.autofix_changes[bugid] = {"comment": {"body": comment}}

    def _get_revisions_with_inactive_authors(self, rev_ids: list) -> Dict[int, dict]:
        revisions = []
        for _rev_ids in Connection.chunks(rev_ids, PHAB_CHUNK_SIZE):
            for revision in self._fetch_revisions(_rev_ids):
                revisions.append(revision)

        user_phids = {revision["fields"]["authorPHID"] for revision in revisions}
        users = self.user_activity.get_phab_users_with_status(list(user_phids))

        result = {}
        for revision in revisions:
            author_info = users[revision["fields"]["authorPHID"]]
            if author_info["status"] != UserStatus.ACTIVE:
                result[revision["id"]] = {
                    "rev_id": revision["id"],
                    "title": revision["fields"]["title"],
                    "author": author_info,
                }
        return result

    @retry(wait=wait_exponential(min=4), stop=stop_after_attempt(5))
    def _fetch_revisions(self, ids: list):
        return self.phab.request(
            "differential.revision.search", constraints={"ids": ids}
        )["data"]


if __name__ == "__main__":
    InactivePatchAuthor().run()
