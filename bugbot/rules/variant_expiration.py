# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
from datetime import datetime, timedelta
from enum import IntEnum, auto
from typing import Dict, Iterable, Optional

import humanize
import requests
import yaml
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla
from requests.exceptions import HTTPError

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.components import ComponentName
from bugbot.history import History
from bugbot.nag_me import Nag

VARIANT_BUG_PAT = re.compile(
    r"^The variant `(.*)` expiration is on (\d{4}-\d{2}-\d{2})$"
)

VARIANTS_PATH = "taskcluster/kinds/test/variants.yml"
VARIANTS_SEARCHFOX_URL = "https://searchfox.org/mozilla-central/source/" + VARIANTS_PATH
VARIANTS_GITHUB_URL = "https://raw.githubusercontent.com/mozilla-firefox/firefox/main/" + VARIANTS_PATH

BUG_DESCRIPTION = f"""
If the variant is not used anymore, please drop it from the [variants.yml]({VARIANTS_SEARCHFOX_URL}) file. If there is a need to keep the variant, please submit a patch to modify the expiration date. Variants will not be scheduled to run after the expiration date.

This bug will be closed automatically once the variant is dropped or the expiration date is updated in the [variants.yml]({VARIANTS_SEARCHFOX_URL}) file.

More information about variants can be found on [Firefox Source Docs](https://firefox-source-docs.mozilla.org/taskcluster/kinds/test.html#variants).

_Note: please do not edit the bug summary or close the bug, it could break the automation._
"""

EXPIRED_VARIANT_COMMENT = f"""
The variant has expired. Expired variants will not be scheduled for testing. Please remove the variant from the [variants.yml]({VARIANTS_SEARCHFOX_URL}) file.
"""


class ExpirationAction(IntEnum):
    """Actions to take on a variant expiration bug"""

    NEEDINFO_TRIAGER = auto()
    SEND_REMINDER = auto()
    CLOSE_EXTENDED = auto()
    CLOSE_DROPPED = auto()
    FILE_NEW_BUG = auto()
    SKIP = auto()

    def __str__(self):
        return self.name.title().replace("_", " ")


class VariantExpiration(BzCleaner, Nag):
    """Track variant expirations

    The following are the actions performed relatively to the variant expiration date:
        - before 30 days: create a bug in the corresponding component
        - before 14 days: needinfo the triage owner if there is no patch
        - before 7 days:  needinfo the triage owner even if there is a patch
        - when expired:
            - comment on the bug
            - send weekly escalation emails
        - If the variant extended or dropped, close the bug as FIXED

    Documentation: https://firefox-source-docs.mozilla.org/taskcluster/kinds/test.html#expired-variants
    """

    def __init__(
        self,
        open_bug_days: int = 30,
        needinfo_no_patch_days: int = 14,
        needinfo_with_patch_days: int = 7,
        cc_on_bugs: Iterable = (
            "jmaher@mozilla.com",
            "smujahid@mozilla.com",
        ),
    ) -> None:
        """Constructor

        Args:
            open_bug_days: number of days before the variant expiration date to
                create a bug.
            needinfo_no_patch_days: number of days before the expiration date to
                needinfo the triage owner if there is no patch.
            needinfo_with_patch_days: number of days before the expiration date
                to needinfo the triage owner even if there is a patch.
            cc_on_bugs: list of emails to cc on the bug.
        """
        super().__init__()

        self.variants = self.get_variants()
        self.today = lmdutils.get_date_ymd("today")
        self.open_bug_date = lmdutils.get_date_ymd(
            self.today + timedelta(open_bug_days)
        )
        self.needinfo_no_patch_date = lmdutils.get_date_ymd(
            self.today + timedelta(needinfo_no_patch_days)
        )
        self.needinfo_with_patch_date = lmdutils.get_date_ymd(
            self.today + timedelta(needinfo_with_patch_days)
        )
        self.cc_on_bugs = list(cc_on_bugs)
        self.ni_extra: Dict[str, dict] = {}

    def description(self) -> str:
        return "Variants that need to be dropped or extended"

    def has_default_products(self) -> bool:
        return False

    def has_product_component(self):
        return True

    def columns(self):
        return ["id", "product", "component", "variant_name", "expiration", "action"]

    def sort_columns(self):
        # sort by expiration date
        return lambda x: [4]

    def escalate(self, person, priority, **kwargs):
        # Escalate based on the number of days since the variant expiration date
        days = (self.today - kwargs["expiration_date"]).days
        return self.escalation.get_supervisor(priority, days, person, **kwargs)

    def get_variants(self) -> dict:
        """Get the variants from the variants.yml file"""

        resp = requests.get(VARIANTS_GITHUB_URL, timeout=20)
        resp.raise_for_status()

        variants = yaml.safe_load(resp.text)
        for variant in variants.values():
            expiration = variant["expiration"]

            if expiration == "never":
                expiration = datetime.max

            variant["expiration"] = lmdutils.get_date_ymd(expiration)

        return variants

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None) -> dict:
        bugs = super().get_bugs(date, bug_ids, chunk_size)

        # Create bugs for variants that will be expired soon
        for variant_name, variant_info in self.variants.items():
            if (
                variant_info.get("bug_id")
                or variant_info["expiration"] >= self.open_bug_date
            ):
                continue

            component = ComponentName.from_str(variant_info["component"])
            expiration = variant_info["expiration"].strftime("%Y-%m-%d")
            new_bug = {
                "summary": f"The variant `{variant_name}` expiration is on {expiration}",
                "product": component.product,
                "component": component.name,
                "status_whiteboard": "[variant-expiration]",
                "type": "task",
                "see_also": self.get_related_bug_ids(variant_name),
                "cc": self.cc_on_bugs,
                "description": BUG_DESCRIPTION,
                "version": "unspecified",
            }

            if self.dryrun or self.test_mode:
                bug = {"id": f"to be created for {variant_name}"}
                logger.info(
                    "A new bug for `%s` will be created with:\n%s",
                    variant_name,
                    new_bug,
                )
            else:
                try:
                    bug = utils.create_bug(new_bug)
                except HTTPError as error:
                    logger.error(
                        "Failed to create a bug for the variant `%s`:\n%s",
                        variant_name,
                        error.response.text,
                        exc_info=error,
                    )
                    continue

            bug_id = str(bug["id"])
            bugs[bug_id] = {
                "id": bug_id,
                "product": component.product,
                "component": component.name,
                "expiration": expiration,
                "variant_name": variant_name,
                "action": ExpirationAction.FILE_NEW_BUG,
            }

        return bugs

    def get_related_bug_ids(self, variant_name: str) -> list:
        """Get the list of bug ids related to the variant"""
        data: list = []

        def handler(bug, data):
            data.append(bug["id"])

        Bugzilla(
            {
                "include_fields": "id",
                "whiteboard": "[variant-expiration]",
                "email1": History.BOT,
                "f1": "short_desc",
                "o1": "casesubstring",
                "v1": f"The variant `{variant_name}` expiration is on",
            },
            bugdata=data,
            bughandler=handler,
        ).wait()

        return data

    def get_followup_action(
        self, bug: dict, variant_name: str, bug_expiration: datetime, has_patch: bool
    ) -> Optional[ExpirationAction]:
        """Get the follow up action for the bug

        Args:
            bug: The bug to handle
            variant_name: The variant id
            bug_expiration: The expiration of the variant as appears in the bug
        """
        variant = self.variants.get(variant_name)
        if variant is None:
            return ExpirationAction.CLOSE_DROPPED

        if "bug_id" in variant:
            logger.error(
                "The variant `%s` is linked to multiple bugs: %s and %s. Variants should be linked to only one open bug",
                variant_name,
                variant["bug_id"],
                bug["id"],
            )
            return None

        variant["bug_id"] = bug["id"]

        if variant["expiration"] > bug_expiration:
            return ExpirationAction.CLOSE_EXTENDED

        if variant["expiration"] < bug_expiration:
            logger.error(
                "Variant expiration for the variant `%s` (bug %s) has been decreased from %s to %s",
                variant_name,
                bug["id"],
                bug_expiration,
                variant["expiration"],
            )
            return None

        if variant["expiration"] <= self.today:
            return ExpirationAction.SEND_REMINDER

        if not self.is_needinfoed(bug):
            if variant["expiration"] <= self.needinfo_with_patch_date or (
                not has_patch and variant["expiration"] <= self.needinfo_no_patch_date
            ):
                return ExpirationAction.NEEDINFO_TRIAGER

        return None

    def get_extra_for_needinfo_template(self):
        return self.ni_extra

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        summary_match = VARIANT_BUG_PAT.match(bug["summary"])
        assert summary_match, f"Bug {bugid} has invalid summary: {bug['summary']}"
        variant_name, bug_expiration = summary_match.groups()
        bug_expiration = lmdutils.get_date_ymd(bug_expiration)
        has_patch = self.is_with_patch(bug)

        action = self.get_followup_action(bug, variant_name, bug_expiration, has_patch)
        if not action:
            return None

        data[bugid] = {
            "action": action,
            "variant_name": variant_name,
            "expiration": bug_expiration.strftime("%Y-%m-%d"),
        }

        if action == ExpirationAction.CLOSE_DROPPED:
            self.autofix_changes[bugid] = {
                "status": "RESOLVED",
                "resolution": "FIXED",
                "comment": {
                    "body": f"The variant has been removed from the [variants.yml]({VARIANTS_SEARCHFOX_URL}) file."
                },
                "flags": [
                    {
                        "id": flag_id,
                        "status": "X",
                    }
                    for flag_id in self.get_needinfo_ids(bug)
                ],
            }

        elif action == ExpirationAction.CLOSE_EXTENDED:
            new_date = self.variants[variant_name]["expiration"].strftime("%Y-%m-%d")
            self.autofix_changes[bugid] = {
                "status": "RESOLVED",
                "resolution": "FIXED",
                "comment": {
                    "body": f"The variant expiration date got extended to {new_date}",
                },
                "flags": [
                    {
                        "id": flag_id,
                        "status": "X",
                    }
                    for flag_id in self.get_needinfo_ids(bug)
                ],
            }

        elif action == ExpirationAction.NEEDINFO_TRIAGER:
            self.ni_extra[bugid] = {
                "has_patch": has_patch,
                "expiration_str": self.get_english_expiration_delta(bug_expiration),
            }
            if not self.add_auto_ni(bugid, utils.get_mail_to_ni(bug)):
                data[bugid]["action"] = ExpirationAction.SKIP

        elif action == ExpirationAction.SEND_REMINDER:
            # Escalate gradually
            if not self.add(
                bug["triage_owner"],
                data[bugid],
                expiration_date=bug_expiration,
            ):
                data[bugid]["action"] = ExpirationAction.SKIP

            if not self.has_expired_comment(bug):
                self.autofix_changes[bugid] = {
                    "comment": {
                        "body": EXPIRED_VARIANT_COMMENT,
                    },
                }

        return bug

    def get_needinfo_ids(self, bug: dict) -> list[str]:
        """Get the IDs of the needinfo flags requested by the bot"""
        return [
            flag["id"]
            for flag in bug.get("flags", [])
            if flag["name"] == "needinfo" and flag["requestee"] == History.BOT
        ]

    def is_with_patch(self, bug: dict) -> bool:
        """Check if the bug has a patch (not obsolete))"""
        return any(
            not attachment["is_obsolete"]
            and (
                attachment["content_type"] == "text/x-phabricator-request"
                or attachment["is_patch"]
            )
            for attachment in bug["attachments"]
        )

    def has_expired_comment(self, bug: dict) -> bool:
        """Check if the bug has the expired comment"""
        return any(
            "The variant has expired." in comment["raw_text"]
            and comment["creator"] == History.BOT
            for comment in bug["comments"]
        )

    def is_needinfoed(self, bug) -> bool:
        """Check if the triager was already needinfo'ed"""
        triage_owner_ni = f"needinfo?({bug['triage_owner']})"

        return any(
            change["field_name"] == "flagtypes.name"
            and change["added"] == triage_owner_ni
            for history in bug["history"]
            if history["who"] == History.BOT
            for change in history["changes"]
        )

    def get_english_expiration_delta(self, expiration_date: datetime) -> str:
        """Get the english delta between today and the expiration date

        Args:
            expiration_date: The expiration date to compare to today

        Returns:
            The english delta

        Examples
            - will expire in a month from now
            - will expire in 14 days from now
            - has expired today
            - has expired a day ago
            - has expired 14 days ago
            - has expired a month ago
        """
        delta = self.today - expiration_date
        if delta.days == 0:
            return "has expired today"

        if delta.days > 0:
            return "has expired " + humanize.naturaltime(delta)

        return "will expire in " + humanize.naturaltime(delta)

    def get_bz_params(self, date: str) -> dict:
        fields = [
            "triage_owner",
            "history",
            "attachments.is_patch",
            "attachments.is_obsolete",
            "attachments.content_type",
            "comments.raw_text",
            "comments.creator",
        ]
        return {
            "include_fields": fields,
            "resolution": "---",
            "status_whiteboard": "[variant-expiration]",
            "email1": History.BOT,
        }


if __name__ == "__main__":
    VariantExpiration().run()
