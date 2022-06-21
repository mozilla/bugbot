# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import List, Optional

from libmozdata import utils as lmdutils
from libmozdata.release_calendar import get_calendar

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.history import History
from auto_nag.team_managers import TeamManagers


class TrackedUnassigned(BzCleaner):
    """Tracked bugs with no assignee"""

    def __init__(
        self,
        target_channels: tuple = ("release", "beta", "nightly"),
        show_soft_freeze_days: int = 14,
    ):
        """Constructor

        Args:
            target_channels: the list of channels that we target to find tracked
                and unassigned bugs.
            show_soft_freeze_days: number of days before the soft freeze date to
                start showing the soft freeze comment in the needinfo requests.
        """
        super().__init__()
        self.init_versions()
        self.version_flags: List[dict] = []
        self.target_channels = target_channels
        self.team_managers = TeamManagers()

        soft_freeze_date = get_calendar()[0]["soft freeze"]
        today = lmdutils.get_date_ymd("today")
        self.soft_freeze_days = (soft_freeze_date - today).days
        self.show_soft_freeze_comment = self.soft_freeze_days <= show_soft_freeze_days
        self.extra_ni = {
            "show_soft_freeze_comment": self.show_soft_freeze_comment,
            "soft_freeze_days": self.soft_freeze_days,
        }
        self.is_weekend = utils.is_weekend(today)

        # Determine the date to decide if a bug will receive a reminder comment
        self.reminder_commit_date = lmdutils.get_date("today", 3)

    def description(self):
        return "Tracked bugs with no assignee"

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "reasons", "is_regression", "action"]

    def handle_bug(self, bug, data):
        last_comment = self._get_last_comment(bug)
        if last_comment:
            if (
                # If we commented before, we want to send reminders when we are
                # close to the soft freeze.
                self.is_weekend
                or not self.show_soft_freeze_comment
                or last_comment["time"] > self.reminder_commit_date
            ):
                return

        bugid = str(bug["id"])

        is_reminder = bool(last_comment)

        bug_trackings = [
            flag
            for flag in self.version_flags
            if bug.get(flag["tracking_field"]) in ("blocking", "+")
            and bug.get(flag["status_field"]) in ("affected", "---")
        ]

        reasons = [
            "{tracking_type} firefox{version} ({channel})".format(
                tracking_type=(
                    "tracked for" if bug[flag["tracking_field"]] == "+" else "blocking"
                ),
                version=flag["version"],
                channel=flag["channel"],
            )
            for flag in bug_trackings
        ]

        # We are using the regressed_by field to identify regression instead of
        # using the regression keyword because we want to suggesting backout. We
        # can only suggest backout if we know the exact cause of the regression.
        is_regression = bool(bug["regressed_by"])

        # This is a workaround to pass the information to get_mail_to_auto_ni()
        bug["is_reminder"] = is_reminder

        data[bugid] = {
            "reasons": reasons,
            "is_regression": is_regression,
            "action": "Reminder comment" if is_reminder else "Needinfo",
        }

        str_reasons = utils.english_list(reasons)
        if is_reminder:
            comment_num = last_comment["count"]
            self.autofix_changes[bugid] = {
                "comment": {
                    "body": (
                        f"This is a reminder regarding [comment #{comment_num}]"
                        f"(https://bugzilla.mozilla.org/show_bug.cgi?id={bugid}#{comment_num})!\n\n"
                        f"The bug is marked as { str_reasons }. "
                        "We have limited time to fix this, "
                        f"the soft freeze is in { self.soft_freeze_days } days. "
                        "However, the bug still isn't assigned."
                    )
                },
            }
        else:
            self.extra_ni[bugid] = {
                "reasons": str_reasons,
                "is_regression": is_regression,
            }

        return bug

    def get_bz_params(self, date):
        fields = [
            "regressed_by",
            "component.team_name",
            "components.team_name",
            "triage_owner",
            "comments",
        ]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "OP",
            "j1": "OR",
        }
        for channel in self.target_channels:
            version = self.versions[channel]
            tracking_field = utils.get_flag(version, "tracking", channel)
            status_field = utils.get_flag(version, "status", channel)
            fields.extend((tracking_field, status_field))

            # We need this to explain the needinfo
            self.version_flags.append(
                {
                    "version": version,
                    "channel": channel,
                    "tracking_field": tracking_field,
                    "status_field": status_field,
                }
            )

            n = int(utils.get_last_field_num(params))
            params.update(
                {
                    f"f{n}": "OP",
                    f"f{n+1}": tracking_field,
                    f"o{n+1}": "anyexact",
                    f"v{n+1}": ["+", "blocking"],
                    f"f{n+2}": status_field,
                    f"o{n+2}": "anyexact",
                    f"v{n+2}": ["---", "affected"],
                    f"f{n+3}": "CP",
                }
            )
        n = int(utils.get_last_field_num(params))
        params[f"f{n}"] = "CP"
        utils.get_empty_assignees(params)

        return params

    def get_mail_to_auto_ni(self, bug):
        # If this is not the first time, we will needinfo no body
        if bug["is_reminder"]:
            return None

        manager = self.team_managers.get_component_manager(bug["component"], False)
        if manager and "bz_email" in manager:
            return {
                "mail": manager["bz_email"],
                "nickname": manager["nick"],
            }

        if not bug["triage_owner"]:
            return None

        return {
            "mail": bug["triage_owner"],
            "nickname": bug["triage_owner_detail"]["nick"],
        }

    @staticmethod
    def _get_last_comment(bug: dict) -> Optional[str]:
        """Get the date of the last comment generated by this tool on the
        provided bug.
        """
        for comment in reversed(bug["comments"]):
            if comment["author"] == History.BOT and comment["text"].startswith(
                "The bug is marked as"
            ):
                return comment["time"]

        return None


if __name__ == "__main__":
    TrackedUnassigned().run()
