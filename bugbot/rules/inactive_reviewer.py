# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
from datetime import datetime
from typing import Dict

from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from libmozdata.connection import Connection
from libmozdata.phabricator import PhabricatorAPI
from tenacity import retry, stop_after_attempt, wait_exponential

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.history import History
from bugbot.inactive_utils import get_revisions, handle_bug_util, process_bugs
from bugbot.user_activity import PHAB_CHUNK_SIZE, UserActivity, UserStatus

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
        bugs, self.query_url = process_bugs(
            bugs, self._get_revisions_with_inactive_reviewers, self._add_needinfo
        )

        return bugs

    def _add_needinfo(self, bugid: str, inactive_revs: list) -> None:
        ni_mails = {rev["author"]["name"] for rev in inactive_revs}
        nicknames = utils.english_list(
            sorted({rev["author"]["nick"] for rev in inactive_revs})
        )
        has_old_patch = any(
            revision["created_at"] < self.old_patch_limit for revision in inactive_revs
        )

        reviewers = {
            (reviewer["phab_username"], reviewer["status_note"])
            for revision in inactive_revs
            for reviewer in revision["reviewers"]
        }
        has_resigned = any(note == "Resigned from review" for _, note in reviewers)

        if len(reviewers) == 1:
            if has_resigned:
                summary = "a reviewer who resigned from the review"
            else:
                summary = "an inactive reviewer"
        else:
            if has_resigned:
                summary = "reviewers who are inactive or resigned from the review"
            else:
                summary = "inactive reviewers"

        comment = self.ni_template.render(
            revisions=inactive_revs,
            nicknames=nicknames,
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
                for ni_mail in ni_mails
            ],
        }

    def _get_revisions_with_inactive_reviewers(self, rev_ids: list) -> Dict[int, dict]:
        return get_revisions(
            Connection.chunks(rev_ids, PHAB_CHUNK_SIZE),
            self._fetch_revisions,
            self.user_activity.get_phab_users_with_status,
            self._get_reviewer_status_note,
            UserStatus.ACTIVE,
        )

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
        return handle_bug_util(
            bug, data, PHAB_FILE_NAME_PAT, PHAB_TABLE_PAT, History.BOT
        )

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
