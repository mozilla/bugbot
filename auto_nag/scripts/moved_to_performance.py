# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import json

from auto_nag.bzcleaner import BzCleaner


class MovedToPerformance(BzCleaner):
    """Add a comment to bugs that recently moved to the performance component"""

    def __init__(self):
        super().__init__()
        self.ni_extra = {}

    def description(self):
        return "Bugs that recently moved to the performance component"

    def get_extra_for_needinfo_template(self):
        return self.ni_extra

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        has_profiler_link = (
            any(
                "https://share.firefox.dev/" in comment["text"]
                for comment in bug["comments"]
            )
            or "https://perf-html.io/from-url/" in bug["url"]
        )

        has_memory_report = any(
            self._is_memory_report_file(attachment)
            for attachment in bug["attachments"]
            if not attachment["is_obsolete"] and not attachment["is_patch"]
        )

        has_troubleshooting_info = any(
            self._is_troubleshooting_content(attachment)
            for attachment in bug["attachments"]
            if not attachment["is_obsolete"] and not attachment["is_patch"]
        )

        if has_profiler_link and has_memory_report and has_troubleshooting_info:
            # Nothing missing, no need to add a comment
            return None

        self.ni_extra[bugid] = {
            "has_profiler_link": has_profiler_link,
            "has_memory_report": has_memory_report,
            "has_troubleshooting_info": has_troubleshooting_info,
        }

        return bug

    @staticmethod
    def _is_memory_report_file(attachment):
        return (
            attachment["content_type"]
            in (
                "application/gzip",
                "application/x-gzip",
                "application/json",
            )
            and "memory-report" in attachment["file_name"]
        )

    @staticmethod
    def _is_troubleshooting_content(attachment):
        if (
            attachment["content_type"]
            not in (
                "application/json",
                "text/plain",
            )
            or "memory-report" in attachment["file_name"]
        ):
            return False

        content_bytes = base64.b64decode(attachment["data"])
        try:
            content = json.loads(content_bytes)
        except ValueError:
            return False

        return all(
            key in content
            for key in (
                "application",
                "processes",
                "addons",
                "startupCache",
                "modifiedPreferences",
            )
        )

    def ignore_meta(self):
        return True

    def get_mail_to_auto_ni(self, bug):
        return {"mail": bug["creator"], "nickname": bug["creator_detail"]["nick"]}

    def get_bz_params(self, date):
        fields = [
            "creator",
            "attachments.is_obsolete",
            "attachments.is_patch",
            "attachments.content_type",
            "attachments.data",
            "attachments.file_name",
            "comments.text",
            "url",
        ]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "bug_type": "defect",
            "f1": "product",
            "o1": "equals",
            "v1": "Core",
            "f2": "component",
            "o2": "equals",
            "v2": "Performance",
            "f3": "component",
            "o3": "changedafter",
            "v3": "-7d",
            "n4": 1,
            "f4": "component",
            "o4": "changedafter",
            "v4": "-1d",
            "n6": 1,
            "f6": "longdesc",
            "o6": "casesubstring",
            "v5": "could you make sure the following information is on this bug?",
        }

        return params


if __name__ == "__main__":
    MovedToPerformance().run()
