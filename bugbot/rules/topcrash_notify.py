# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.nag_me import Nag


class TopcrashNotify(BzCleaner, Nag):
    def __init__(self):
        super(TopcrashNotify, self).__init__()
        self.nweeks = utils.get_config(self.name(), "number_of_weeks", 1)

    def description(self):
        return "Bugs with a ni on a bug with topcrash keyword without activity for the last {} {}".format(
            self.nweeks, utils.plural("week", self.nweeks)
        )

    def get_extra_for_template(self):
        return {"nweeks": self.nweeks}

    def get_extra_for_nag_template(self):
        return self.get_extra_for_template()

    def has_last_comment_time(self):
        return True

    def has_needinfo(self):
        return True

    def columns(self):
        return ["id", "summary", "needinfos", "last_comment"]

    def columns_nag(self):
        return ["id", "summary", "to", "from", "last_comment"]

    def get_priority(self, bug):
        return "normal"

    def set_people_to_nag(self, bug, buginfo):
        priority = self.get_priority(bug)
        if not self.filter_bug(priority):
            return None

        has_manager = False
        for flag in bug["flags"]:
            if flag.get("name", "") == "needinfo" and flag["status"] == "?":
                requestee = flag["requestee"]
                buginfo["to"] = requestee
                moz_name = self.get_people().get_moz_name(flag["setter"])
                buginfo["from"] = moz_name if moz_name is not None else flag["setter"]
                if self.add(requestee, buginfo, priority=priority):
                    has_manager = True

        if not has_manager:
            self.add_no_manager(buginfo["id"])

        return bug

    def get_bz_params(self, date):
        fields = ["flags", "_custom"]
        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "days_elapsed",
            "o1": "greaterthan",
            "v1": self.nweeks * 7,
            "f2": "flagtypes.name",
            "o2": "casesubstring",
            "v2": "needinfo?",
            "f3": "keywords",
            "o3": "anyexact",
            "v3": ["topcrash", "topcrash-startup"],
            "f4": "keywords",
            "o4": "nowords",
            "v4": ["meta", "stalled"],
        }

        return params


if __name__ == "__main__":
    TopcrashNotify().run()
