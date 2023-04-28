# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.people import People


class LeaveOpenNoActivity(BzCleaner):
    def __init__(self):
        super(LeaveOpenNoActivity, self).__init__()
        self.people = People.get_instance()
        self.nmonths = utils.get_config(self.name(), "months_lookup")
        self.max_ni = utils.get_config(self.name(), "max_ni")
        self.skiplist = set(utils.get_config(self.name(), "skiplist", []))

    def description(self):
        return "Bugs with leave-open keyword and no activity for the last {} months".format(
            self.nmonths
        )

    def get_extra_for_needinfo_template(self):
        return self.get_extra_for_template()

    def get_extra_for_template(self):
        return {"nmonths": self.nmonths}

    def get_auto_ni_skiplist(self):
        return super().get_auto_ni_skiplist() | self.skiplist

    def get_max_ni(self):
        return self.max_ni

    def get_mail_to_auto_ni(self, bug):
        for field in ["assigned_to", "triage_owner"]:
            person = bug.get(field, "")
            if person and self.people.is_mozilla(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None

    def get_bz_params(self, date):
        fields = ["assigned_to", "triage_owner"]
        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "keywords",
            "o1": "casesubstring",
            "v1": "leave-open",
            "f2": "keywords",
            "o2": "nowordssubstr",
            "v2": "intermittent,stalled,meta",
            "f3": "status_whiteboard",
            "o3": "notregexp",
            "v3": r"\[(test|stockwell) disabled.*\]",
            "f4": "days_elapsed",
            "o4": "greaterthan",
            "v4": self.nmonths * 30,
            "n5": 1,
            "f5": "longdesc",
            "o5": "casesubstring",
            "v5": "The leave-open keyword is there and there is no activity for",
        }

        return params


if __name__ == "__main__":
    LeaveOpenNoActivity().run()
