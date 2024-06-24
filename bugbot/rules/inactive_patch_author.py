# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
from typing import Dict, List

from libmozdata.connection import Connection
from libmozdata.phabricator import PhabricatorAPI
from tenacity import retry, stop_after_attempt, wait_exponential

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.user_activity import PHAB_CHUNK_SIZE, UserActivity, UserStatus

PHAB_FILE_NAME_PAT = re.compile(r"phabricator-D([0-9]+)-url\.txt")


class InactivePatchAuthors(BzCleaner):
    """Bugs with patches authored by inactive patch authors"""

    def __init__(self):
        super(InactivePatchAuthors, self).__init__()
        self.phab = PhabricatorAPI(utils.get_login_info()["phab_api_key"])
        self.user_activity = UserActivity(include_fields=["nick"], phab=self.phab)

    def description(self):
        return "Bugs with inactive patch authors"

    def columns(self):
        return ["id", "summary", "revisions"]

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)
        rev_ids = {rev_id for bug in bugs.values() for rev_id in bug["rev_ids"]}
        inactive_authors = self._get_inactive_patch_authors(list(rev_ids))

        for bugid, bug in list(bugs.items()):
            inactive_patches = [
                {"rev_id": rev_id, "author": inactive_authors[rev_id]}
                for rev_id in bug["rev_ids"]
                if rev_id in inactive_authors
            ]

            if inactive_patches:
                bug["inactive_patches"] = inactive_patches
                print(f"Bug {bugid} has inactive patches: {inactive_patches}")
            else:
                del bugs[bugid]

        return bugs

    def _get_inactive_patch_authors(self, rev_ids: list) -> Dict[int, dict]:
        revisions: List[dict] = []

        for _rev_ids in Connection.chunks(rev_ids, PHAB_CHUNK_SIZE):
            for revision in self._fetch_revisions(_rev_ids):
                author_phid = revision["fields"]["authorPHID"]
                created_at = revision["fields"]["dateCreated"]
                if author_phid == "PHID-USER-eltrc7x5oplwzfguutrb":
                    continue
                revisions.append(
                    {
                        "rev_id": revision["id"],
                        "author_phid": author_phid,
                        "created_at": created_at,
                    }
                )

        user_phids = set()

        for revision in revisions:
            user_phids.add(revision["author_phid"])

        users = self.user_activity.get_phab_users_with_status(
            list(user_phids), keep_active=False
        )

        result: Dict[int, dict] = {}
        for revision in revisions:
            author_phid = revision["author_phid"]

            if author_phid not in users:
                continue

            author_info = users[author_phid]
            if author_info["status"] == UserStatus.INACTIVE:
                result[revision["rev_id"]] = {
                    "name": author_info["name"],
                    "status": author_info["status"],
                    "last_active": author_info.get("last_seen_date"),
                }

        return result

    @retry(
        wait=wait_exponential(min=4),
        stop=stop_after_attempt(5),
    )
    def _fetch_revisions(self, ids: list):
        return self.phab.request(
            "differential.revision.search",
            constraints={"ids": ids},
        )["data"]

    def handle_bug(self, bug, data):
        rev_ids = [
            int(attachment["file_name"][13:-8])
            for attachment in bug["attachments"]
            if attachment["content_type"] == "text/x-phabricator-request"
            and PHAB_FILE_NAME_PAT.match(attachment["file_name"])
            and not attachment["is_obsolete"]
        ]

        if not rev_ids:
            return

        bugid = str(bug["id"])
        data[bugid] = {
            "rev_ids": rev_ids,
        }
        return bug

    def get_bz_params(self, date):
        fields = [
            "comments.raw_text",
            "comments.creator",
            "attachments.file_name",
            "attachments.content_type",
            "attachments.is_obsolete",
        ]
        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "attachments.ispatch",
            "o1": "equals",
            "v1": "1",
        }

        return params


if __name__ == "__main__":
    InactivePatchAuthors().run()
