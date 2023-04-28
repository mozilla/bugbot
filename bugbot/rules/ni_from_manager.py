# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.nag_me import Nag


class NiFromManager(BzCleaner, Nag):
    def __init__(self):
        super(NiFromManager, self).__init__()
        self.nweeks = utils.get_config(self.name(), "number_of_weeks", 1)
        self.vip = self.get_people().get_rm_or_directors()
        self.white_list = utils.get_config(self.name(), "white-list", [])
        self.black_list = utils.get_config(self.name(), "black-list", [])
        if not self.init_versions():
            return

        self.status_flags = (
            utils.get_flag(self.versions["central"], "status", "central"),
            utils.get_flag(self.versions["beta"], "status", "beta"),
            utils.get_flag(self.versions["release"], "status", "release"),
            utils.get_flag(self.versions["esr_previous"], "status", "esr"),
            utils.get_flag(self.versions["esr"], "status", "esr"),
        )

    def description(self):
        return "Bugs with a ni on a bug marked as affecting a released version without activity for the last {} {}".format(
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

        for flag in self.status_flags:
            if flag not in bug:
                logger.warning(f"Bug {bug['id']} doesn't have flag {flag}")
                return None

        any_affected = any(bug[flag] == "affected" for flag in self.status_flags)

        has_manager = False
        accepted = False
        for flag in bug["flags"]:
            if (
                flag.get("name", "") == "needinfo"
                and flag["status"] == "?"
                and (flag["setter"] in self.vip or any_affected)
            ):
                requestee = flag["requestee"]
                if self.is_under(requestee):
                    accepted = True
                    buginfo["to"] = requestee
                    moz_name = self.get_people().get_moz_name(flag["setter"])
                    buginfo["from"] = (
                        moz_name if moz_name is not None else flag["setter"]
                    )
                    if self.add(requestee, buginfo, priority=priority):
                        has_manager = True

        if accepted and not has_manager:
            self.add_no_manager(buginfo["id"])

        return bug if accepted else None

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
            # Either needinfo from a release manager...
            "f3": "OP",
            "j3": "OR",
            "f4": "setters.login_name",
            "o4": "anyexact",
            "v4": ",".join(self.vip),
            # ...or needinfo from anyone on a bug still tracked by a release manager.
            "f5": "cf_status_firefox_release",
            "o5": "equals",
            "v5": "affected",
            "f6": "cf_status_firefox_beta",
            "o6": "equals",
            "v6": "affected",
            "f7": "cf_status_firefox_nightly",
            "o7": "equals",
            "v7": "affected",
            "f8": "cf_status_firefox_esr",
            "o8": "equals",
            "v8": "affected",
            "f9": "CP",
        }

        return params


if __name__ == "__main__":
    NiFromManager().run()
