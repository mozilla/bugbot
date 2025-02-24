# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import timedelta

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import BugzillaUser

from bugbot.bzcleaner import BzCleaner
from bugbot.constants import BOT_MAIN_ACCOUNT
from bugbot.utils import is_bot_email

RESOLUTION_KEYWORDS = (
    "backedout",
    "backed out",
    "back out",
    "backout",
    "wontfix",
    "invalid",
    "incomplete",
    "duplicate",
    "fixed",
    "resolved",
    "resolve",
    "resolution",
)


class PerfAlertResolvedRegression(BzCleaner):
    def __init__(self, max_seconds_before_status=86400):
        """
        Initializes the bugbot rule for ensuring performance alerts
        have a valid resolution comment when they are closed.

        max_seconds_before_status int: When a resolution comment is not provided
            at the time of resolution, the preceding comment can be considered as a
            resolution comment as long it hasn't been more than `max_seconds_before_status`
            seconds since the comment was made. Only applies when the resolution
            author is different from the preceding comment author, otherwise, the
            comment is accepted without checking the time that has elapsed.
        """
        super().__init__()
        self.max_seconds_before_status = max_seconds_before_status
        self.extra_ni = {}

    def description(self):
        return "PerfAlert regressions whose resolution has changed recently"

    def columns(self):
        return [
            "id",
            "summary",
            "status",
            "status_author",
            "resolution",
            "resolution_comment",
            "resolution_previous",
            "needinfo",
        ]

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def get_bz_params(self, date):
        end_date = lmdutils.get_date_ymd("today")
        start_date = end_date - timedelta(1)

        fields = [
            "id",
            "history",
            "comments.text",
            "comments.creation_time",
            "comments.author",
        ]

        # Find all bugs that have perf-alert, and regression in their keywords. Search
        # for bugs that have been changed in the last day. Only look for bugs after
        # October 1st, 2024 to prevent triggering comments on older performance regressions
        params = {
            "include_fields": fields,
            "f3": "creation_ts",
            "o3": "greaterthan",
            "v3": "2024-10-01T00:00:00Z",
            "f1": "regressed_by",
            "o1": "isnotempty",
            "f2": "keywords",
            "o2": "allwords",
            "v2": ["regression", "perf-alert"],
            "f4": "resolution",
            "o4": "changedafter",
            "v4": start_date,
            "f5": "resolution",
            "o5": "changedbefore",
            "v5": end_date,
        }

        return params

    def should_needinfo(self, bug_comments, status_time):
        # Check if the bugbot has already needinfo'ed on the bug since
        # the last status change before making one
        for comment in bug_comments[::-1]:
            if comment["creation_time"] <= status_time:
                break

            if comment["author"] == BOT_MAIN_ACCOUNT:
                if (
                    "could you provide a comment explaining the resolution?"
                    in comment["text"]
                ):
                    # Bugbot has already commented on this bug since the last
                    # status change. No need to comment again since this was
                    # just a resolution change
                    return False

        return True

    def get_resolution_comments(self, comments, status_time):
        resolution_comment = None
        preceding_comment = None

        for comment in comments:
            if comment["creation_time"] > status_time:
                break
            if comment["creation_time"] == status_time:
                resolution_comment = comment
            if not is_bot_email(comment["author"]):
                preceding_comment = comment

        return resolution_comment, preceding_comment

    def get_resolution_comment(self, comments, bug_history):
        status_time = bug_history["status_time"]
        resolution_comment, preceding_comment = self.get_resolution_comments(
            comments, status_time
        )

        if (
            resolution_comment
            and resolution_comment["author"] == bug_history["status_author"]
        ):
            # Accept if status author provided a comment at the same time
            return resolution_comment["text"]
        if preceding_comment:
            if preceding_comment["author"] == bug_history["status_author"]:
                # Accept if status author provided a comment before setting
                # resolution
                return preceding_comment["text"]

            preceding_resolution_comment = f"{preceding_comment['text']} (provided by {preceding_comment['author']})"
            if any(
                keyword in preceding_comment["text"].lower()
                for keyword in RESOLUTION_KEYWORDS
            ):
                # Accept if a non-status author provided a comment before a
                # resolution was set, and hit some keywords
                return preceding_resolution_comment
            if (
                lmdutils.get_timestamp(status_time)
                - lmdutils.get_timestamp(preceding_comment["creation_time"])
            ) < self.max_seconds_before_status:
                # Accept if the previous comment from another author is
                # within the time limit
                return preceding_resolution_comment

        return None

    def get_resolution_history(self, bug):
        bug_info = {}

        # Get the last resolution change that was made in this bug
        for change in bug["history"][::-1]:
            # Get the most recent resolution change first, this is because
            # it could have changed since the status was changed and by who
            if not bug_info.get("resolution"):
                for specific_change in change["changes"]:
                    if specific_change["field_name"] == "resolution":
                        bug_info["resolution"] = specific_change["added"]
                        bug_info["resolution_previous"] = (
                            specific_change["removed"].strip() or "---"
                        )
                        bug_info["resolution_time"] = change["when"]
                        break

            if bug_info.get("resolution"):
                # Find the status that the bug was resolved to, and by who
                for specific_change in change["changes"]:
                    if specific_change["field_name"] == "status" and specific_change[
                        "added"
                    ] in ("RESOLVED", "REOPENED"):
                        bug_info["status"] = specific_change["added"]
                        bug_info["status_author"] = change["who"]
                        bug_info["status_time"] = change["when"]
                        break

            if bug_info.get("status"):
                break

        return bug_info

    def set_autofix(self, bugs):
        for bug_id, bug_info in bugs.items():
            if bug_info["needinfo"]:
                self.extra_ni[bug_id] = {
                    "resolution": bug_info["resolution"],
                    "status": bug_info["status"],
                }
                self.add_auto_ni(
                    bug_id,
                    {
                        "mail": bug_info["status_author"],
                        "nickname": bug_info["nickname"],
                    },
                )

    def get_needinfo_nicks(self, bugs):
        def _user_handler(user, data):
            data[user["name"]] = user["nick"]

        authors_to_ni = set()
        for bug_id, bug_info in bugs.items():
            if bug_info["needinfo"]:
                authors_to_ni.add(bug_info["status_author"])

        if not authors_to_ni:
            return

        user_emails_to_names = {}
        BugzillaUser(
            user_names=list(authors_to_ni),
            include_fields=["nick", "name"],
            user_handler=_user_handler,
            user_data=user_emails_to_names,
        ).wait()

        for bug_id, bug_info in bugs.items():
            if bug_info["needinfo"]:
                bug_info["nickname"] = user_emails_to_names[bug_info["status_author"]]

    def handle_bug(self, bug, data):
        # Match all the resolutions with resolution comments if they exist
        bug_id = str(bug["id"])
        bug_comments = bug["comments"]
        bug_history = self.get_resolution_history(bug)

        bug_history["needinfo"] = False
        bug_history["resolution_comment"] = self.get_resolution_comment(
            bug_comments, bug_history
        )
        if bug_history["resolution_comment"] is None:
            # Use N/A to signify no resolution comment was provided
            bug_history["resolution_comment"] = "N/A"
            bug_history["needinfo"] = self.should_needinfo(
                bug_comments, bug_history["status_time"]
            )

        data[bug_id] = bug_history

        return bug

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        self.get_needinfo_nicks(bugs)
        self.set_autofix(bugs)
        return bugs


if __name__ == "__main__":
    PerfAlertResolvedRegression().run()
