# # This Source Code Form is subject to the terms of the Mozilla Public
# # License, v. 2.0. If a copy of the MPL was not distributed with this file,
# # You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import re
from typing import Dict, List

from libmozdata.connection import Connection
from libmozdata.phabricator import ConduitError, PhabricatorAPI
from tenacity import retry, stop_after_attempt, wait_exponential

from bugbot import people, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.nag_me import Nag
from bugbot.user_activity import PHAB_CHUNK_SIZE, UserActivity, UserStatus

logging.basicConfig(level=logging.DEBUG)
PHAB_FILE_NAME_PAT = re.compile(r"phabricator-D([0-9]+)-url\.txt")


class InactivePatchAuthors(BzCleaner, Nag):
    """Bugs with patches authored by inactive patch authors"""

    def __init__(self):
        super().__init__()
        self.phab = PhabricatorAPI(utils.get_login_info()["phab_api_key"])
        self.user_activity = UserActivity(phab=self.phab)
        self.default_assignees = utils.get_default_assignees()
        self.people = people.People.get_instance()
        self.no_bugmail = True

    def description(self):
        return "Bugs with inactive patch authors"

    def columns(self):
        return ["id", "summary"]

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
                self.unassign_inactive_author(bugid, bug, inactive_patches)
                self.add([bug["assigned_to"], bug["triage_owner"]], bug)
            else:
                del bugs[bugid]

        return bugs

    def nag_template(self):
        return self.name() + ".html"

    def unassign_inactive_author(self, bugid, bug, inactive_patches):
        prod = bug["product"]
        comp = bug["component"]
        default_assignee = self.default_assignees[prod][comp]
        autofix = {"assigned_to": default_assignee}

        comment = (
            "The patch author is inactive on Bugzilla, so the assignee is being reset."
        )
        autofix["comment"] = {"body": comment}

        # Abandon the patches
        for patch in inactive_patches:
            rev_id = patch["rev_id"]
            revision = self.phab.request(
                "differential.revision.search",
                constraints={"ids": [rev_id]},
            )["data"][0]
            try:
                if revision["fields"]["status"]["value"] in [
                    "needs-review",
                    "needs-revision",
                    "accepted",
                    "changed-planned",
                ]:
                    self.phab.request(
                        "differential.revision.edit",
                        objectIdentifier=rev_id,
                        transactions=[{"type": "abandon", "value": True}],
                    )
                    logging.info(f"Abandoned patch {rev_id} for bug {bugid}.")
                else:
                    logging.info(f"Patch {rev_id} for bug {bugid} is already closed.")

            except ConduitError as e:
                logging.error(f"Failed to abandon patch {rev_id} for bug {bugid}: {e}")

        self.autofix_changes[bugid] = autofix

    def _get_inactive_patch_authors(self, rev_ids: list) -> Dict[int, dict]:
        revisions: List[dict] = []

        for _rev_ids in Connection.chunks(rev_ids, PHAB_CHUNK_SIZE):
            for revision in self._fetch_revisions(_rev_ids):
                author_phid = revision["fields"]["authorPHID"]
                created_at = revision["fields"]["dateCreated"]
                revisions.append(
                    {
                        "rev_id": revision["id"],
                        "author_phid": author_phid,
                        "created_at": created_at,
                        "status": revision["fields"]["status"]["value"],
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
            "product": bug["product"],
            "component": bug["component"],
            "assigned_to": bug["assigned_to"],
            "triage_owner": bug["triage_owner"],
        }
        return bug

    def get_bz_params(self, date):
        fields = [
            "comments.raw_text",
            "comments.creator",
            "attachments.file_name",
            "attachments.content_type",
            "attachments.is_obsolete",
            "product",
            "component",
            "assigned_to",
            "triage_owner",
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
