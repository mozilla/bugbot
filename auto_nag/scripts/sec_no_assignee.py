# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.team_managers import TeamManagers

DEFAULT_SEC_KEYWORDS = ("sec-moderate", "sec-high", "sec-critical")


class SecNoAssignee(BzCleaner):
    """Security bugs with no assignee"""

    def __init__(self, wait_days: int = 3, sec_keywords: tuple = DEFAULT_SEC_KEYWORDS):
        """Constructor

        Args:
            wait_days: the waiting period in days before sending a needinfo
                request. The period will be calculated based on the bug creation
                date.
            sec_keywords: if a bug has any of these keywords, it will be
                considered a security bug.
        """
        super().__init__()
        self.team_managers = TeamManagers()
        self.wait_days = wait_days
        self.sec_keywords = sec_keywords

    def description(self):
        return "Security bugs, no assignee and older than {} days".format(
            self.wait_days
        )

    def get_extra_for_template(self):
        return {"ndays": self.wait_days}

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def ignore_meta(self):
        return True

    def has_last_comment_time(self):
        return True

    def has_product_component(self):
        return True

    def columns(self):
        return ["component", "id", "summary", "last_comment"]

    def get_mail_to_auto_ni(self, bug):
        manager = self.team_managers.get_component_manager(bug["component"], False)
        if manager and "bz_email" in manager:
            return {
                "mail": manager["bz_email"],
                "nickname": manager["nick"],
            }

        if bug["triage_owner"]:
            return {
                "mail": bug["triage_owner"],
                "nickname": bug["triage_owner_detail"]["nick"],
            }

        return None

    def get_bz_params(self, date):
        fields = ["triage_owner"]
        params = {
            "bug_type": "defect",
            "include_fields": fields,
            "resolution": "---",
            "f1": "keywords",
            "o1": "anyexact",
            "v1": list(self.sec_keywords),
            "n2": 1,
            "f2": "keywords",
            "o2": "anyexact",
            "v2": ["testcase-wanted", "stalled"],
            "f3": "creation_ts",
            "o3": "lessthaneq",
            "v3": f"-{self.wait_days}d",
            "f4": "flagtypes.name",
            "o4": "notequals",
            "v4": "needinfo?",
            "n6": 1,
            "f6": "longdesc",
            "o6": "casesubstring",
            "v6": "There is no assignee and the security bug is opened for more than",
        }

        utils.get_empty_assignees(params)

        return params


if __name__ == "__main__":
    SecNoAssignee().run()
