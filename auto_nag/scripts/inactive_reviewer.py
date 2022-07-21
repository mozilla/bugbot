# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
from datetime import datetime
from typing import Dict, List

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from libmozdata.connection import Connection
from libmozdata.phabricator import PhabricatorAPI
from tenacity import retry, stop_after_attempt, wait_exponential

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.history import History
from auto_nag.user_activity import PHAB_CHUNK_SIZE, UserActivity, UserStatus

PHAB_FILE_NAME_PAT = re.compile(r"phabricator-D([0-9]+)-url\.txt")
PHAB_TABLE_PAT = re.compile(r"^\|\ \[D([0-9]+)\]\(h", flags=re.M)


class InactiveReviewer(BzCleaner):
    """Bugs with patches that are waiting for review from inactive reviewers"""

    def __init__(self, old_patch_months: int = 6):
        """Constructor

        Args:
            old_patch_months: number of months since creation of the patch to be
                considered old. If the bug has an old patch, we will mention
                abandon the patch as an option.
        """
        super(InactiveReviewer, self).__init__()
        self.phab = PhabricatorAPI(utils.get_login_info()["phab_api_key"])
        self.user_activity = UserActivity(include_fields=["nick"], phab=self.phab)
        self.ni_template = self.get_needinfo_template()
        self.old_patch_limit = (
            lmdutils.get_date_ymd("today") - relativedelta(months=old_patch_months)
        ).timestamp()

    def description(self):
        return "Bugs with inactive patch reviewers"

    def columns(self):
        return ["id", "summary", "revisions"]

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)

        rev_ids = {rev_id for bug in bugs.values() for rev_id in bug["rev_ids"]}
        revisions = self._get_revisions_with_inactive_reviewers(list(rev_ids))

        for bugid, bug in list(bugs.items()):
            inactive_revs = [
                revisions[rev_id] for rev_id in bug["rev_ids"] if rev_id in revisions
            ]
            if inactive_revs:
                bug["revisions"] = inactive_revs
                self._add_needinfo(bugid, inactive_revs)
            else:
                del bugs[bugid]

        # Resolving https://github.com/mozilla/relman-auto-nag/issues/1300 should clean this
        # including improve the wording in the template (i.e., "See the search query on Bugzilla").
        self.query_url = utils.get_bz_search_url({"bug_id": ",".join(bugs.keys())})

        return bugs

    def _add_needinfo(self, bugid: str, inactive_revs: list) -> None:
        ni_mails = {rev["author"]["name"] for rev in inactive_revs}
        nicknames = utils.english_list(
            sorted({rev["author"]["nick"] for rev in inactive_revs})
        )
        has_old_patch = any(
            revision["created_at"] < self.old_patch_limit for revision in inactive_revs
        )
        comment = self.ni_template.render(
            revisions=inactive_revs,
            nicknames=nicknames,
            has_old_patch=has_old_patch,
            plural=utils.plural,
            documentation=self.get_documentation(),
        )

        self.autofix_changes[bugid] = {
            "comment": {"body": comment},
            "flags": [
                {
                    "name": "needinfo",
                    "requestee": ni_mail,
                    "status": "?",
                    "new": "true",
                }
                for ni_mail in ni_mails
            ],
        }

    def _get_revisions_with_inactive_reviewers(self, rev_ids: list) -> Dict[int, dict]:
        revisions: List[dict] = []
        for _rev_ids in Connection.chunks(rev_ids, PHAB_CHUNK_SIZE):
            for revision in self._fetch_revisions(_rev_ids):
                if (
                    len(revision["attachments"]["reviewers"]["reviewers"]) == 0
                    or revision["fields"]["status"]["value"] != "needs-review"
                    or revision["fields"]["isDraft"]
                ):
                    continue

                reviewers = [
                    {
                        "phid": reviewer["reviewerPHID"],
                        "is_group": reviewer["reviewerPHID"].startswith("PHID-PROJ"),
                        "is_blocking": reviewer["isBlocking"],
                        "is_accepted": reviewer["status"] == "accepted",
                        "is_resigned": reviewer["status"] == "resigned",
                    }
                    for reviewer in revision["attachments"]["reviewers"]["reviewers"]
                ]

                # Group reviewers will be consider always active; so if there is
                # no other reviewers blocking, we don't need to check further.
                if any(
                    reviewer["is_group"] or reviewer["is_accepted"]
                    for reviewer in reviewers
                ) and not any(
                    not reviewer["is_accepted"]
                    for reviewer in reviewers
                    if reviewer["is_blocking"]
                ):
                    continue

                revisions.append(
                    {
                        "rev_id": revision["id"],
                        "title": revision["fields"]["title"],
                        "created_at": revision["fields"]["dateCreated"],
                        "author_phid": revision["fields"]["authorPHID"],
                        "reviewers": reviewers,
                    }
                )

        user_phids = set()
        for revision in revisions:
            user_phids.add(revision["author_phid"])
            for reviewer in revision["reviewers"]:
                user_phids.add(reviewer["phid"])

        users = self.user_activity.get_phab_users_with_status(
            list(user_phids), keep_active=True
        )

        result: Dict[int, dict] = {}
        for revision in revisions:
            # It is not useful to notify an inactive author about an inactive
            # reviewer, thus we should exclude revisions with inactive authors.
            author_info = users[revision["author_phid"]]
            if author_info["status"] != UserStatus.ACTIVE:
                continue

            revision["author"] = author_info

            inactive_reviewers = []
            for reviewer in revision["reviewers"]:
                if reviewer["is_group"]:
                    continue

                reviewer_info = users[reviewer["phid"]]
                if (
                    not reviewer["is_resigned"]
                    and reviewer_info["status"] == UserStatus.ACTIVE
                ):
                    continue

                reviewer["info"] = reviewer_info
                inactive_reviewers.append(reviewer)

            if len(inactive_reviewers) == len(revision["reviewers"]) or any(
                reviewer["is_blocking"] and not reviewer["is_accepted"]
                for reviewer in inactive_reviewers
            ):
                revision["reviewers"] = [
                    {
                        "phab_username": reviewer["info"]["phab_username"],
                        "status_note": self._get_reviewer_status_note(reviewer),
                    }
                    for reviewer in inactive_reviewers
                ]
                result[revision["rev_id"]] = revision

        return result

    @staticmethod
    def _get_reviewer_status_note(reviewer: dict) -> str:
        if reviewer["is_resigned"]:
            return "Resigned from review"

        status = reviewer["info"]["status"]
        if status == UserStatus.UNAVAILABLE:
            until = reviewer["info"]["unavailable_until"]
            if until:
                return_date = datetime.fromtimestamp(until).strftime("%b %-d, %Y")
                return f"Back {return_date}"

            return "Unavailable"

        if status == UserStatus.DISABLED:
            return "Disabled"

        return "Inactive"

    @retry(
        wait=wait_exponential(min=4),
        stop=stop_after_attempt(5),
    )
    def _fetch_revisions(self, ids: list):
        return self.phab.request(
            "differential.revision.search",
            constraints={"ids": ids},
            attachments={"reviewers": True},
        )["data"]

    def handle_bug(self, bug, data):
        rev_ids = [
            int(PHAB_FILE_NAME_PAT.findall(attachment["file_name"])[0])
            for attachment in bug["attachments"]
            if attachment["content_type"] == "text/x-phabricator-request"
            and not attachment["is_obsolete"]
        ]

        if not rev_ids:
            return

        # We should not comment about the same patch more than once.
        rev_ids_with_ni = set()
        for comment in bug["comments"]:
            if comment["creator"] == History.BOT and comment["raw_text"].startswith(
                "The following patch"
            ):
                rev_ids_with_ni.update(
                    int(id) for id in PHAB_TABLE_PAT.findall(comment["raw_text"])
                )

        if rev_ids_with_ni:
            rev_ids = [id for id in rev_ids if id not in rev_ids_with_ni]

        if not rev_ids:
            return

        # It will be nicer to show a sorted list of patches
        rev_ids.sort()

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
            "f1": "attachments.mimetype",
            "o1": "equals",
            "v1": "text/x-phabricator-request",
        }

        return params


if __name__ == "__main__":
    InactiveReviewer().run()
