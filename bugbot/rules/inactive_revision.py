# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from dateutil.relativedelta import relativedelta
from jinja2 import Environment, FileSystemLoader, Template
from libmozdata import utils as lmdutils
from libmozdata.connection import Connection
from libmozdata.phabricator import PhabricatorAPI
from tenacity import retry, stop_after_attempt, wait_exponential

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.history import History
from bugbot.user_activity import PHAB_CHUNK_SIZE, UserActivity

PHAB_FILE_NAME_PAT = re.compile(r"phabricator-D([0-9]+)-url\.txt")
PHAB_TABLE_PAT = re.compile(r"^\|\ \[D([0-9]+)\]\(h", flags=re.M)


class InactiveRevision(BzCleaner):
    """Bugs with inactive patches that are awaiting action from authors or reviewers."""

    def __init__(self, old_patch_months: int = 6, patch_activity_months: int = 6):
        """Constructor

        Args:
            old_patch_months: number of months since creation of the patch to be
                considered old. If the bug has an old patch, we will mention
                abandon the patch as an option.
            patch_activity_months: Number of months since the last activity on the patch.
        """
        super(InactiveRevision, self).__init__()
        self.phab = PhabricatorAPI(utils.get_login_info()["phab_api_key"])
        self.user_activity = UserActivity(include_fields=["nick"], phab=self.phab)
        self.ni_author_template = self.load_template(
            self.name() + "_needinfo_author.txt"
        )
        self.ni_reviewer_template = self.load_template(
            self.name() + "_needinfo_reviewer.txt"
        )
        self.old_patch_limit = (
            lmdutils.get_date_ymd("today") - relativedelta(months=old_patch_months)
        ).timestamp()
        self.patch_activity_limit = (
            lmdutils.get_date_ymd("today") - relativedelta(months=patch_activity_months)
        ).timestamp()
        self.max_actions = utils.get_config(self.name(), "max_actions", 1)

    def description(self):
        return "Bugs with inactive patches that are awaiting action from authors or reviewers."

    def get_max_actions(self):
        return self.max_actions

    def columns(self):
        return ["id", "summary", "revisions", "needinfo_user"]

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)

        rev_ids = {rev_id for bug in bugs.values() for rev_id in bug["rev_ids"]}
        revisions = self._get_revisions_with_inactive_action(list(rev_ids))

        for bugid, bug in list(bugs.items()):
            inactive_revs = [
                revisions[rev_id] for rev_id in bug["rev_ids"] if rev_id in revisions
            ]
            if inactive_revs:
                bug["revisions"] = inactive_revs
                needinfo_user = self._add_needinfo(bugid, inactive_revs)
                bug["needinfo_user"] = needinfo_user
            else:
                del bugs[bugid]

        self.query_url = utils.get_bz_search_url({"bug_id": ",".join(bugs.keys())})

        return bugs

    def load_template(self, template_filename: str) -> Template:
        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template(template_filename)
        return template

    def _add_needinfo(self, bugid: str, inactive_revs: list) -> str:
        has_old_patch = any(
            revision["created_at"] < self.old_patch_limit for revision in inactive_revs
        )

        for revision in inactive_revs:
            last_action_by, _ = self._find_last_action(revision["rev_id"])
            if last_action_by == "author" and revision["reviewers"]:
                ni_mail = revision["reviewers"][0]["phab_username"]
                summary = (
                    "The last action was by the author, so needinfoing the reviewer."
                )
                template = self.ni_reviewer_template
                nickname = revision["reviewers"][0]["phab_username"]
            elif last_action_by == "reviewer":
                ni_mail = revision["author"]["phab_username"]
                summary = (
                    "The last action was by the reviewer, so needinfoing the author."
                )
                template = self.ni_author_template
                nickname = revision["author"]["phab_username"]
            else:
                continue

            comment = template.render(
                revisions=[revision],
                nicknames=nickname,
                reviewers_status_summary=summary,
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
                ],
            }
            return nickname
        return ""

    def _find_last_action(self, revision_id):
        details = self._fetch_revisions([revision_id])

        if not details:
            return None, None

        revision = details[0]
        author_phid = revision["fields"]["authorPHID"]
        reviewers = [
            reviewer["reviewerPHID"]
            for reviewer in revision["attachments"]["reviewers"]["reviewers"]
        ]

        transactions = self._fetch_revision_transactions(revision["phid"])
        if not transactions:
            return "unknown", None

        filtered_transactions = [
            transaction
            for transaction in transactions
            if transaction["authorPHID"] == author_phid
            or transaction["authorPHID"] in reviewers
        ]

        if not filtered_transactions:
            return "unknown", None

        last_transaction = filtered_transactions[0]
        last_action_by_phid = last_transaction["authorPHID"]

        if last_action_by_phid == author_phid:
            last_action_by = "author"
        else:
            last_action_by = "reviewer"

        return last_action_by, last_transaction

    def _get_revisions_with_inactive_action(self, rev_ids: list) -> dict[int, dict]:
        revisions: list[dict] = []

        for _rev_ids in Connection.chunks(rev_ids, PHAB_CHUNK_SIZE):
            for revision in self._fetch_revisions(_rev_ids):
                if (
                    len(revision["attachments"]["reviewers"]["reviewers"]) == 0
                    or revision["fields"]["status"]["value"] != "needs-review"
                    or revision["fields"]["isDraft"]
                ):
                    continue

                _, last_transaction = self._find_last_action(revision["id"])

                if (
                    not last_transaction
                    or last_transaction["dateCreated"] >= self.patch_activity_limit
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

                if any(
                    reviewer["is_group"] or reviewer["is_accepted"]
                    for reviewer in reviewers
                ) and all(
                    reviewer["is_accepted"]
                    for reviewer in reviewers
                    if reviewer["is_blocking"]
                ):
                    continue

                reviewers = [
                    reviewer for reviewer in reviewers if not reviewer["is_resigned"]
                ]

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

        result: dict[int, dict] = {}
        for revision in revisions:
            author_phid = revision["author_phid"]
            if author_phid in users:
                author_info = users[author_phid]
                revision["author"] = author_info
            else:
                continue

            reviewers = []
            for reviewer in revision["reviewers"]:
                reviewer_phid = reviewer["phid"]
                if reviewer_phid in users:
                    reviewer_info = users[reviewer_phid]
                    reviewer["info"] = reviewer_info
                else:
                    continue
                reviewers.append(reviewer)

            revision["reviewers"] = [
                {
                    "phab_username": reviewer["info"]["phab_username"],
                }
                for reviewer in reviewers
            ]
            result[revision["rev_id"]] = revision

        return result

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

    def _fetch_revision_transactions(self, revision_phid):
        response = self.phab.request(
            "transaction.search", objectIdentifier=revision_phid
        )
        return response["data"]

    def handle_bug(self, bug, data):
        rev_ids = [
            # To avoid loading the attachment content (which can be very large),
            # we extract the revision id from the file name, which is in the
            # format of "phabricator-D{revision_id}-url.txt".
            # len("phabricator-D") == 13
            # len("-url.txt") == 8
            int(attachment["file_name"][13:-8])
            for attachment in bug["attachments"]
            if attachment["content_type"] == "text/x-phabricator-request"
            and PHAB_FILE_NAME_PAT.match(attachment["file_name"])
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
    InactiveRevision().run()
