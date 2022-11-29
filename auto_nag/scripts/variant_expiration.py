# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
from datetime import datetime, timedelta
from enum import IntEnum, auto
from typing import Iterable, Optional

import requests
import yaml
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla

from auto_nag import logger, utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.components import ComponentName
from auto_nag.history import History
from auto_nag.nag_me import Nag

VARIANT_BUG_PAT = re.compile(
    r"^The variant `(.*)` expiration is on (\d{4}-\d{2}-\d{2})$"
)

VARIANTS_PATH = "taskcluster/ci/test/variants.yml"
VARIANTS_SEARCHFOX_URL = "https://searchfox.org/mozilla-central/source/" + VARIANTS_PATH
VARIANTS_HG_URL = "https://hg.mozilla.org/mozilla-central/raw-file/tip/" + VARIANTS_PATH

BUG_DESCRIPTION = f"""
If the variant is not used anymore, please drop it from the [variants.yml]({VARIANTS_SEARCHFOX_URL}) file. If there is a need to keep the variant, please submit a patch to modify the expiration date. Variants will not be scheduled to run after the expiration date.

This bug will be closed automatically once the variant is dropped or the expiration date is updated in the [variants.yml]({VARIANTS_SEARCHFOX_URL}) file.

More information about variants can be found on [Firefox Source Docs](https://firefox-source-docs.mozilla.org/taskcluster/kinds/test.html#variants).

_Note: please do not edit the bug summery or close the bug, it could break the automation._
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

    The following is the actions:
        - If the variant is expiring soon, create a bug in the corresponding component
        - Set a needinfo flag on the triager when the variant becomes expired
        - If the variant is still expired, escalate by sending emails
        - If the variant extended or dropped, close the bug as FIXED

    Documentation: https://firefox-source-docs.mozilla.org/taskcluster/kinds/test.html#expired-variants
    """

    def __init__(
        self,
        open_bug_days: int = 30,
        reminder_days: int = 0,
        cc_on_bugs: Iterable = (
            "jmaher@mozilla.com",
            "smujahid@mozilla.com",
        ),
    ) -> None:
        """Constructor

        Args:
            open_bug_days: number of days before the variant expiration date to
                create a bug.
            reminder_days: number of days after the variant expiration date to
                start sending reminders.
            cc_on_bugs: list of emails to cc on the bug.
        """
        super().__init__()

        self.variants = self.get_variants()
        today = lmdutils.get_date_ymd("today")
        self.open_bug_date = lmdutils.get_date_ymd(today + timedelta(open_bug_days))
        self.reminder_date = lmdutils.get_date_ymd(today + timedelta(reminder_days))
        self.cc_on_bugs = list(cc_on_bugs)

    def description(self) -> str:
        return "Variants that need to be updated or dropped"

    def has_default_products(self) -> bool:
        return False

    def has_product_component(self):
        return True

    def columns(self):
        return ["id", "product", "component", "variant_id", "expiration", "action"]

    def sort_columns(self):
        # sort by expiration date
        return lambda x: [4]

    def escalate(self, person, priority, **kwargs):
        # Escalate based on the number of days since the variant expiration date
        days = (kwargs["expiration_date"] - self.nag_date).days
        return self.escalation.get_supervisor(priority, days, person, **kwargs)

    def get_variants(self) -> dict:
        """Get the variants from the variants.yml file"""

        resp = requests.get(VARIANTS_HG_URL, timeout=20)
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
        for variant_id, variant_info in self.variants.items():
            if (
                variant_info.get("bug_id")
                or variant_info["expiration"] >= self.open_bug_date
            ):
                continue

            component = ComponentName.from_str(variant_info["component"])
            expiration = variant_info["expiration"].strftime("%Y-%m-%d")
            new_bug = {
                "summary": f"The variant `{variant_id}` expiration is on {expiration}",
                "product": component.product,
                "component": component.name,
                "status_whiteboard": "[variant-expiration]",
                "type": "task",
                "see_also": self.get_related_bug_ids(variant_id),
                "cc": self.cc_on_bugs,
                "description": BUG_DESCRIPTION,
            }

            if self.dryrun or self.test_mode:
                bug = {"id": f"to be created for {variant_id}"}
                logger.info(
                    "A new bug for `%s` will be created with:\n%s", variant_id, new_bug
                )
            else:
                bug = utils.create_bug(new_bug)

            bug_id = str(bug["id"])
            bugs[bug_id] = {
                "id": bug_id,
                "product": component.product,
                "component": component.name,
                "expiration": expiration,
                "variant_id": variant_id,
                "action": ExpirationAction.FILE_NEW_BUG,
            }

        return bugs

    def get_related_bug_ids(self, variant_id: str) -> list:
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
                "v1": f"The variant `{variant_id}` expiration is on",
            },
            bugdata=data,
            bughandler=handler,
        ).wait()

        return data

    def get_followup_action(
        self, bug: dict, variant_id: str, bug_expiration: datetime
    ) -> Optional[ExpirationAction]:
        """Get the follow up action for the bug

        Args:
            bug: The bug to handle
            variant_id: The variant id
            bug_expiration: The expiration of the variant as appears in the bug
        """
        variant = self.variants.get(variant_id)
        if variant is None:
            return ExpirationAction.CLOSE_DROPPED

        assert "bug_id" not in variant, "Variant should not be linked to multiple bugs"
        variant["bug_id"] = bug["id"]

        if variant["expiration"] > bug_expiration:
            return ExpirationAction.CLOSE_EXTENDED

        if variant["expiration"] < bug_expiration:
            raise Exception("Variant expiration should not be decreased")

        if variant["expiration"] <= self.reminder_date:
            if not self.is_needinfoed(bug):
                return ExpirationAction.NEEDINFO_TRIAGER

            return ExpirationAction.SEND_REMINDER

        return None

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        summary_match = VARIANT_BUG_PAT.match(bug["summary"])
        assert summary_match, f"Bug {bugid} has invalid summary: {bug['summary']}"
        variant_id, bug_expiration = summary_match.groups()
        bug_expiration = lmdutils.get_date_ymd(bug_expiration)

        action = self.get_followup_action(bug, variant_id, bug_expiration)
        if not action:
            return None

        data[bugid] = {
            "action": action,
            "variant_id": variant_id,
            "expiration": bug_expiration.strftime("%Y-%m-%d"),
        }

        if action == ExpirationAction.CLOSE_DROPPED:
            self.autofix_changes[bugid] = {
                "status": "RESOLVED",
                "resolution": "FIXED",
                "comment": {
                    "body": f"The variant has been removed from the [variants.yml]({VARIANTS_SEARCHFOX_URL}) file."
                },
            }
        elif action == ExpirationAction.CLOSE_EXTENDED:
            new_date = self.variants[variant_id]["expiration"].strftime("%Y-%m-%d")
            self.autofix_changes[bugid] = {
                "status": "RESOLVED",
                "resolution": "FIXED",
                "comment": {
                    "body": f"Expiration date is extended to {new_date}",
                },
            }
        elif action == ExpirationAction.NEEDINFO_TRIAGER:
            if not self.add_auto_ni(bugid, utils.get_mail_to_ni(bug)):
                data[bugid]["action"] = ExpirationAction.SKIP

        elif action == ExpirationAction.SEND_REMINDER:
            # Escalate gradually
            if not self.add(
                bug["triage_owner"], data[bugid], expiration_date=bug_expiration
            ):
                data[bugid]["action"] = ExpirationAction.SKIP

        return bug

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

    def get_bz_params(self, date: str) -> dict:
        fields = [
            "triage_owner",
            "history",
        ]
        return {
            "include_fields": fields,
            "resolution": "---",
            "status_whiteboard": "[variant-expiration]",
            "email1": History.BOT,
        }


if __name__ == "__main__":
    VariantExpiration().run()
