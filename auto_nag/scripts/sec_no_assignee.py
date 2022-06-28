# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.team_managers import TeamManagers


class SecNoAssignee(BzCleaner):
    def __init__(self):
        super(SecNoAssignee, self).__init__()
        self.team_managers = TeamManagers()
        self.ndays = self.get_config("ndays", 3)

    def description(self):
        return "Security bugs, no assignee and older than {} days".format(self.ndays)

    def get_extra_for_template(self):
        return {"ndays": self.ndays}

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
            "o1": "anywordssubstr",
            "v1": ",".join(self.get_config("sec-types")),
            "f2": "keywords",
            "o2": "nowordssubstr",
            "v2": "testcase-wanted,stalled",
            "f3": "creation_ts",
            "o3": "lessthaneq",
            "v3": f"-{self.ndays}d",
            "f4": "flagtypes.name",
            "o4": "notequals",
            "v4": "needinfo?",
            "f5": "priority",
            "o5": "anyexact",
            "v5": "p1,p2",
            "n6": 1,
            "f6": "longdesc",
            "o6": "casesubstring",
            "v6": "There is no assignee and the security bug is opened for more than",
        }

        utils.get_empty_assignees(params)

        return params


if __name__ == "__main__":
    SecNoAssignee().run()
