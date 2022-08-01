# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.history import History
from auto_nag.nag_me import Nag

# TODO: should be moved when resolving https://github.com/mozilla/relman-auto-nag/issues/1384
LOW_SEVERITY = ["S3", "normal", "S4", "minor", "trivial", "enhancement"]


class FuzzBlockers(BzCleaner, Nag):
    def __init__(self, waiting_days: int = 3):
        """Constructor

        Args:
            waiting_days: number of days to wait after the bug creation before
                starting to nag.
        """
        super().__init__()

        self.waiting_days = waiting_days

    def description(self):
        return "Bugs that prevent fuzzing from making progress"

    def nag_template(self):
        return super().template()

    def set_people_to_nag(self, bug, buginfo):
        persons = [
            bug["assigned_to"],
            bug["triage_owner"],
        ]
        if not self.add(persons, buginfo):
            self.add_no_manager(buginfo["id"])

        return bug

    def get_mail_to_auto_ni(self, bug):
        if bug["severity"] in LOW_SEVERITY and not self._is_commented(bug):
            return utils.get_mail_to_ni(bug)

    @staticmethod
    def _is_commented(bug: dict) -> bool:
        """Get whether the bug has a previous comment by this tool"""
        for comment in reversed(bug["comments"]):
            if comment["creator"] == History.BOT and comment["raw_text"].startswith(
                "This bug prevents fuzzing from making progress."
            ):
                return True

        return False

    def get_bz_params(self, date):
        fields = [
            "triage_owner",
            "assigned_to",
            "severity",
            "comments.raw_text",
            "comments.creator",
        ]
        return {
            "include_fields": fields,
            "bug_status": ["UNCONFIRMED", "NEW", "ASSIGNED", "REOPENED"],
            "f1": "status_whiteboard",
            "o1": "substring",
            "v1": "[fuzzblocker]",
            "f2": "creation_ts",
            "o2": "lessthaneq",
            "v2": f"-{self.waiting_days}d",
            "f3": "creation_ts",
            "o3": "greaterthan",
            "v3": "2021-07-01",
        }


if __name__ == "__main__":
    FuzzBlockers().run()
