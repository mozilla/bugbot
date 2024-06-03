# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from libmozdata.phabricator import PhabricatorAPI

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.user_activity import UserActivity

PHAB_FILE_NAME_PAT = re.compile(r"phabricator-D([0-9]+)-url\.txt")
PHAB_TABLE_PAT = re.compile(r"^\|\ \[D([0-9]+)\]\(h", flags=re.M)


class InactiveRevision(BzCleaner):
    """Bugs with patches that are waiting for review from inactive reviewers"""

    def __init__(self, old_patch_months: int = 6):
        """Constructor

        Args:
            old_patch_months: number of months since creation of the patch to be
                considered old. If the bug has an old patch, we will mention
                abandon the patch as an option.
        """
        super(InactiveRevision, self).__init__()
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
        revisions = self._get_revisions_with_inactive_action(list(rev_ids))

        for bugid, bug in list(bugs.items()):
            inactive_revs = [
                revisions[rev_id] for rev_id in bug["rev_ids"] if rev_id in revisions
            ]
            if inactive_revs:
                bug["revisions"] = inactive_revs
                self._add_needinfo(bugid, inactive_revs)
            else:
                del bugs[bugid]

        self.query_url = utils.get_bz_search_url({"bug_id": ",".join(bugs.keys())})

        return bugs

    def _add_needinfo(self, bugid: str, inactive_revs: list) -> None:
        for revision in inactive_revs:
            last_action_by, _ = self._find_last_action(revision["rev_id"])

            if last_action_by == "author":
                ni_mail = revision["reviewers"][0]["phab_username"]
                summary = (
                    "The last action was by the author, so needinfoing the reviewer."
                )
            elif last_action_by == "reviewer":
                ni_mail = revision["author"]["phab_username"]
                summary = (
                    "The last action was by the reviewer, so needinfoing the author."
                )
            else:
                continue

            comment = self.ni_template.render(
                revisions=[revision],
                nicknames=revision["author"]["nick"],
                reviewers_status_summary=summary,
                has_old_patch=revision["created_at"] < self.old_patch_limit,
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

    def _find_last_action(self, revision_id):
        details = self._fetch_revision_details(revision_id)

        if not details:
            return None, None

        revision = details[0]
        author_phid = revision["fields"]["authorPHID"]
        reviewers = [
            reviewer["reviewerPHID"]
            for reviewer in revision["attachments"]["reviewers"]["reviewers"]
        ]

        transactions = self._fetch_revision_transactions(revision["phid"])

        last_transaction = None
        for transaction in transactions:
            if (
                last_transaction is None
                or transaction["dateCreated"] > last_transaction["dateCreated"]
            ):
                last_transaction = transaction

        if last_transaction:
            last_action_by_phid = last_transaction["authorPHID"]
            if last_action_by_phid == author_phid:
                last_action_by = "author"
            elif last_action_by_phid in reviewers:
                last_action_by = "reviewer"
            else:
                last_action_by = "other"
        else:
            last_action_by = "unknown"

        return last_action_by, last_transaction
