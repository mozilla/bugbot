# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Optional

import humanize
from libmozdata import utils as lmdutils
from libmozdata.fx_trains import FirefoxTrains

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.constants import LOW_PRIORITY, LOW_SEVERITY
from bugbot.history import History
from bugbot.team_managers import TeamManagers


class TrackedAttention(BzCleaner):
    """Tracked bugs that need attention"""

    def __init__(
        self,
        target_channels: tuple = ("esr", "release", "beta", "nightly"),
        show_soft_freeze_days: int = 14,
        reminder_interval: int = 5,
    ):
        """Constructor

        Args:
            target_channels: the list of channels that we target to find tracked
                and unassigned bugs.
            show_soft_freeze_days: number of days before the soft freeze date to
                start showing the soft freeze comment in the needinfo requests.
            reminder_interval: number of days to wait before posting a reminder
                comment. We remind only if the bug is not assigned, it is not a
                weekend, and we are close to the soft-freeze date.
        """
        super().__init__()
        if not self.init_versions():
            return

        self.team_managers = TeamManagers()

        schedule = FirefoxTrains.get_instance().get_release_schedule("nightly")
        soft_freeze_date = lmdutils.get_date_ymd(schedule["soft_code_freeze"])
        today = lmdutils.get_date_ymd("today")
        soft_freeze_delta = soft_freeze_date - today

        self.is_soft_freeze_soon = 0 < soft_freeze_delta.days <= show_soft_freeze_days
        self.soft_freeze_delta = (
            "today"
            if soft_freeze_delta.days == 0
            else f"in { humanize.naturaldelta(soft_freeze_delta)}"
        )
        self.extra_ni = {
            "soft_freeze_delta": self.soft_freeze_delta,
        }

        # Determine the date to decide if a bug will receive a reminder comment
        self.reminder_comment_date = lmdutils.get_date(today, reminder_interval)
        self.is_weekend = utils.is_weekend(today)

        self.version_flags = [
            {
                "version": self.versions[channel],
                "channel": channel,
                "tracking_field": utils.get_flag(
                    self.versions[channel], "tracking", channel
                ),
                "status_field": utils.get_flag(
                    self.versions[channel], "status", channel
                ),
            }
            for channel in target_channels
        ]

    def description(self):
        return "Tracked bugs that need attention"

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return [
            "id",
            "summary",
            "tracking_statuses",
            "is_regression",
            "reasons",
            "action",
        ]

    def handle_bug(self, bug, data):
        is_no_assignee = utils.is_no_assignee(bug["assigned_to"])
        last_comment = self._get_last_comment(bug)

        # If we commented before, we want to send reminders when we are close to
        # the soft freeze.
        is_reminder = bool(last_comment)
        if is_reminder:
            if self.is_weekend or not is_no_assignee or not self.is_soft_freeze_soon:
                return None

            # Post reminders based on the configured interval
            last_reminder_comment = self._get_last_reminder_comment(bug)
            last_comment_time = (
                last_reminder_comment["time"]
                if last_reminder_comment
                else last_comment["time"]
            )
            if last_comment_time > self.reminder_comment_date:
                return None

        bugid = str(bug["id"])

        def format_flag(flag: dict) -> str:
            tracking_type = (
                "tracked for" if bug[flag["tracking_field"]] == "+" else "blocking"
            )
            version = flag["version"]
            channel = flag["channel"]
            return f"{tracking_type} firefox{version} ({channel})"

        tracking_statuses = [
            format_flag(flag)
            for flag in self.version_flags
            if bug.get(flag["tracking_field"]) in ("blocking", "+")
            and bug.get(flag["status_field"]) in ("affected", "---")
        ]
        assert tracking_statuses

        reasons = []
        solutions = []
        if is_no_assignee:
            reasons.append("isn't assigned")
            solutions.append("find an assignee")
        if bug["priority"] in LOW_PRIORITY:
            reasons.append("has low priority")
            solutions.append("increase the priority")
        if not is_reminder and bug["severity"] in LOW_SEVERITY:
            reasons.append("has low severity")
            solutions.append("increase the severity")
        assert reasons and solutions

        # We are using the regressed_by field to identify regression instead of
        # using the regression keyword because we want to suggesting backout. We
        # can only suggest backout if we know the exact cause of the regression.
        is_regression = bool(bug["regressed_by"])

        # This is a workaround to pass the information to get_mail_to_auto_ni()
        bug["is_reminder"] = is_reminder

        data[bugid] = {
            "tracking_statuses": tracking_statuses,
            "reasons": reasons,
            "is_regression": is_regression,
            "action": "Reminder comment" if is_reminder else "Needinfo",
        }

        if is_reminder:
            assert self.is_soft_freeze_soon
            comment_num = last_comment["count"]
            self.autofix_changes[bugid] = {
                "comment": {
                    "body": (
                        f"This is a reminder regarding comment #{comment_num}!\n\n"
                        f"The bug is marked as { utils.english_list(tracking_statuses) }. "
                        "We have limited time to fix this, "
                        f"the soft freeze is { self.soft_freeze_delta }. "
                        f"However, the bug still { utils.english_list(reasons) }."
                    )
                },
            }
        else:
            need_action = is_no_assignee or bug["priority"] in LOW_PRIORITY
            self.extra_ni[bugid] = {
                "tracking_statuses": utils.english_list(tracking_statuses),
                "reasons": utils.english_list(reasons),
                "solutions": utils.english_list(solutions),
                "show_soft_freeze_comment": self.is_soft_freeze_soon and need_action,
                "show_regression_comment": is_regression and need_action,
            }

        return bug

    def get_bz_params(self, date):
        fields = [
            "regressed_by",
            "product",
            "component",
            "triage_owner",
            "assigned_to",
            "comments",
            "severity",
            "priority",
        ]
        for flag in self.version_flags:
            fields.extend((flag["tracking_field"], flag["status_field"]))

        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "keywords",
            "o1": "nowords",
            "v1": "intermittent-failure",
            "f2": "status_whiteboard",
            "o2": "notsubstring",
            "v2": "[stockwell]",
            "f3": "short_desc",
            "o3": "notregexp",
            "v3": r"^Perma |Intermittent ",
            "j4": "OR",
            "f4": "OP",
            "f5": "bug_severity",
            "o5": "anyexact",
            "v5": list(LOW_SEVERITY),
            "f6": "priority",
            "o6": "anyexact",
            "v6": list(LOW_PRIORITY),
        }
        utils.get_empty_assignees(params)
        n = utils.get_last_field_num(params)
        params[f"f{n}"] = "CP"

        self._amend_tracking_params(params)

        return params

    def _amend_tracking_params(self, params: dict) -> None:
        n = utils.get_last_field_num(params)
        params.update(
            {
                f"j{n}": "OR",
                f"f{n}": "OP",
            }
        )

        for flag in self.version_flags:
            n = int(utils.get_last_field_num(params))
            params.update(
                {
                    f"f{n}": "OP",
                    f"f{n+1}": flag["tracking_field"],
                    f"o{n+1}": "anyexact",
                    f"v{n+1}": ["+", "blocking"],
                    f"f{n+2}": flag["status_field"],
                    f"o{n+2}": "anyexact",
                    f"v{n+2}": ["---", "affected"],
                    f"f{n+3}": "CP",
                }
            )

        n = utils.get_last_field_num(params)
        params[f"f{n}"] = "CP"

    def get_mail_to_auto_ni(self, bug):
        # If this is not the first time, we will needinfo no body
        if bug["is_reminder"]:
            return None

        manager = self.team_managers.get_component_manager(
            bug["product"], bug["component"], False
        )
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
    def _get_last_comment(bug: dict) -> Optional[dict]:
        """Get the the last comment generated by this rule"""
        for comment in reversed(bug["comments"]):
            if comment["author"] == History.BOT and comment["text"].startswith(
                "The bug is marked as"
            ):
                return comment

        return None

    @staticmethod
    def _get_last_reminder_comment(bug: dict) -> Optional[dict]:
        """Get the the last comment generated by this rule"""
        for comment in reversed(bug["comments"]):
            if comment["author"] == History.BOT and comment["text"].startswith(
                "This is a reminder regarding"
            ):
                return comment

        return None


if __name__ == "__main__":
    TrackedAttention().run()
