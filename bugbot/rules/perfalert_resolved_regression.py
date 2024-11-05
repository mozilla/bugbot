# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from libmozdata.bugzilla import Bugzilla

from bugbot.bzcleaner import BzCleaner


class PerfAlertInactiveRegression(BzCleaner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_email_info = {}
        self._bug_history = {}
        self._bug_comments = {}

    def description(self):
        return "PerfAlert regressions whose resolution has changed recently"

    def get_bz_params(self, date):
        fields = [
            "id",
            "resolution",
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
            "v4": date,
        }

        return params

    def get_extra_for_template(self):
        return self.extra_email_info

    def get_resolution_comments(self, bugs):
        # Match all the resolutions with resolution comments if they exist
        for bug_id, bug in bugs.items():
            bug_comments = self._bug_comments.get(bug_id, [])
            bug_history = self._bug_history.get(bug_id, {})

            # Sometimes a resolution comment is not provided so use a default
            bug_history["resolution_comment"] = "No resolution comment provided."
            for comment in bug_comments[::-1]:
                if (
                    comment["creation_time"] == bug_history["resolution_time"]
                    and comment["author"] == bug_history["resolution_author"]
                ):
                    bug_history["resolution_comment"] = comment["text"]
                    break

            self.extra_email_info[bug_id] = bug_history

    def comment_handler(self, bug, bug_id, bugs):
        # Gather all comments to match them with the history after
        self._bug_comments[bug_id] = bug["comments"]

    def history_handler(self, bug):
        bug_info = self._bug_history.setdefault(str(bug["id"]), {})

        # Get the last resolution change that was made in this bug
        for change in bug["history"][::-1]:
            for specific_change in change["changes"]:
                if specific_change["field_name"] == "status" and specific_change[
                    "added"
                ] in ("RESOLVED", "REOPENED"):
                    bug_info["resolution_time"] = change["when"]
                    bug_info["resolution_author"] = change["who"]
                    bug_info["resolution"] = specific_change["added"]
                    break
            if bug_info.get("resolution_author"):
                break

    def gather_bugs_info(self, bugs):
        Bugzilla(
            bugids=self.get_list_bugs(bugs),
            historyhandler=self.history_handler,
            commenthandler=self.comment_handler,
            commentdata=bugs,
            comment_include_fields=["text", "creation_time", "author"],
        ).get_data().wait()

        # Match the history with comments to get resolution reasons
        self.get_resolution_comments(bugs)

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        self.gather_bugs_info(bugs)
        return bugs


if __name__ == "__main__":
    PerfAlertInactiveRegression().run()
