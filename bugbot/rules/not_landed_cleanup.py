# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
from typing import Any

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla
from libmozdata.phabricator import (
    PhabricatorAPI,
    PhabricatorRevisionNotFoundException,
)

from bugbot import db, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.rules.not_landed import (
    NEEDINFO_TRACKING_PREFIX,
    NOT_LANDED_COMMENT_MARKER,
    PHAB_URL_PAT,
)

NOT_LANDED_RULE = "not_landed"
CLOSED_STATUSES = {"RESOLVED", "VERIFIED", "CLOSED"}


class NotLandedCleanup(BzCleaner):
    def __init__(self):
        super().__init__()
        self.phab = PhabricatorAPI(utils.get_login_info()["phab_api_key"])

    def description(self):
        return "Clear obsolete needinfos created by the not_landed rule"

    def filter_no_nag_keyword(self):
        return False

    def has_last_comment_time(self):
        return True

    def get_bz_params(self, date):
        return {
            "include_fields": ["flags", "status"],
            "f1": "flagtypes.name",
            "o1": "substring",
            "v1": "needinfo?",
            "f2": "setters.login_name",
            "o2": "equals",
            "v2": utils.get_config("common", "bot_bz_mail")[0],
            "f3": "longdesc",
            "o3": "casesubstring",
            "v3": NOT_LANDED_COMMENT_MARKER,
        }

    def handle_bug(self, bug, data):
        data[str(bug["id"])] = {
            "flags": bug["flags"],
            "status": bug["status"],
        }
        return bug

    def commenthandler(self, bug, bugid, data):
        data[str(bugid)]["comments"] = bug["comments"]

    @staticmethod
    def get_not_landed_needinfos(bug: dict[str, Any]) -> list[dict[str, Any]]:
        bot_accounts = utils.get_config("common", "bot_bz_mail")
        comment_times = {
            comment["creation_time"]
            for comment in bug.get("comments", [])
            if comment["creator"] in bot_accounts
            and NOT_LANDED_COMMENT_MARKER in comment["text"]
        }
        return [
            flag
            for flag in bug.get("flags", [])
            if flag["name"] == "needinfo"
            and flag["status"] == "?"
            and flag["setter"] in bot_accounts
            and flag["creation_date"] in comment_times
        ]

    @staticmethod
    def get_revision_tracking(
        changes: list[Any], bugids: set[str]
    ) -> dict[str, set[int] | None]:
        tracked: dict[str, set[int] | None] = dict.fromkeys(bugids)
        for change in changes:
            bugid = str(change.bugid)
            if bugid not in tracked:
                continue
            extra = change.extra.extra if change.extra else ""
            if not extra.startswith(NEEDINFO_TRACKING_PREFIX):
                continue
            revision_ids = tracked[bugid]
            if revision_ids is None:
                revision_ids = tracked[bugid] = set()
            revision_ids.update(
                int(revision_id)
                for revision_id in extra.removeprefix(NEEDINFO_TRACKING_PREFIX).split(
                    ","
                )
                if revision_id
            )
        return tracked

    def get_tracked_revision_ids(self, bugids: set[str]) -> dict[str, set[int] | None]:
        changes = list(db.BugChange.get(name=NOT_LANDED_RULE))
        changes += list(db.BugChange.get(name=self.name()))
        changes.sort(key=lambda change: change.id)
        return self.get_revision_tracking(changes, bugids)

    def get_landed_bug_ids(self, revision_ids_by_bug: dict[str, set[int]]) -> set[str]:
        landed = set()
        for bugid, revision_ids in revision_ids_by_bug.items():
            if not revision_ids:
                continue
            all_published = True
            for revision_id in revision_ids:
                try:
                    revision = self.phab.load_revision(rev_id=revision_id)
                except PhabricatorRevisionNotFoundException:
                    all_published = False
                    break
                if revision["fields"]["status"].get("value") != "published":
                    all_published = False
                    break
            if all_published:
                landed.add(bugid)
        return landed

    def get_phab_attachments(
        self, bugids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        attachment_ids: list[int] = []

        def attachment_id_handler(attachments, bugid, data):
            for attachment in attachments:
                if (
                    attachment["content_type"] == "text/x-phabricator-request"
                    and attachment["is_obsolete"] == 0
                ):
                    data.append(attachment["id"])

        Bugzilla(
            bugids=bugids,
            attachmenthandler=attachment_id_handler,
            attachmentdata=attachment_ids,
            attachment_include_fields=["is_obsolete", "content_type", "id"],
        ).get_data().wait()

        attachments_by_bug: dict[str, list[dict[str, Any]]] = {}

        def attachment_handler(attachments, data):
            for attachment in attachments:
                data.setdefault(str(attachment["bug_id"]), []).append(attachment)

        if attachment_ids:
            Bugzilla(
                attachmentids=attachment_ids,
                attachmenthandler=attachment_handler,
                attachmentdata=attachments_by_bug,
                attachment_include_fields=["bug_id", "creation_time", "data"],
            ).get_data().wait()

        return attachments_by_bug

    def get_legacy_revision_ids(
        self, needinfos_by_bug: dict[str, list[dict[str, Any]]]
    ) -> dict[str, set[int]]:
        attachments_by_bug = self.get_phab_attachments(list(needinfos_by_bug))
        revisions_by_bug: dict[str, set[int]] = {}
        for bugid, needinfos in needinfos_by_bug.items():
            requested_at = min(
                lmdutils.get_timestamp(flag["creation_date"]) for flag in needinfos
            )
            for attachment in attachments_by_bug.get(bugid, []):
                if lmdutils.get_timestamp(attachment["creation_time"]) > requested_at:
                    continue
                phab_url = base64.b64decode(attachment["data"]).decode("utf-8")
                match = PHAB_URL_PAT.search(phab_url)
                if match:
                    revisions_by_bug.setdefault(bugid, set()).add(int(match.group(1)))
        return revisions_by_bug

    def record_revision_ids(self, revisions_by_bug: dict[str, set[int]]) -> None:
        if getattr(self, "dryrun", True) or self.test_mode:
            return
        for bugid, revision_ids in revisions_by_bug.items():
            extra = NEEDINFO_TRACKING_PREFIX + ",".join(
                str(revision_id) for revision_id in sorted(revision_ids)
            )
            db.BugChange.add(self.name(), bugid, extra=extra)

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super().get_bugs(date=date, bug_ids=bug_ids)
        needinfos_by_bug = {
            bugid: needinfos
            for bugid, bug in bugs.items()
            if (needinfos := self.get_not_landed_needinfos(bug))
        }
        revision_ids_by_bug = self.get_tracked_revision_ids(set(needinfos_by_bug))

        legacy_needinfos = {
            bugid: needinfos
            for bugid, needinfos in needinfos_by_bug.items()
            if revision_ids_by_bug[bugid] is None
        }
        recovered_revision_ids = self.get_legacy_revision_ids(legacy_needinfos)
        legacy_revision_ids = {
            bugid: recovered_revision_ids.get(bugid, set())
            for bugid in legacy_needinfos
        }
        revision_ids_by_bug.update(legacy_revision_ids)
        self.record_revision_ids(legacy_revision_ids)

        clear_bugids = {
            bugid
            for bugid in needinfos_by_bug
            if bugs[bugid]["status"] in CLOSED_STATUSES
        }
        open_revisions = {}
        for bugid in needinfos_by_bug:
            if bugid in clear_bugids:
                continue
            revision_ids = revision_ids_by_bug[bugid]
            assert revision_ids is not None
            open_revisions[bugid] = revision_ids
        clear_bugids |= self.get_landed_bug_ids(open_revisions)
        clear_bugids = set(sorted(clear_bugids, key=int)[: self.normal_changes_max])

        self.autofix_changes = {
            bugid: {
                "flags": [
                    {"id": flag["id"], "status": "X"}
                    for flag in needinfos_by_bug[bugid]
                ]
            }
            for bugid in clear_bugids
        }
        return {bugid: bugs[bugid] for bugid in clear_bugids}

    def get_email_data(self, date):
        # Run the autofix pipeline without sending a summary email.
        super().get_email_data(date)
        return []


if __name__ == "__main__":
    NotLandedCleanup().run()
