# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import utils as lmdutils

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.escalation import Escalation
from auto_nag.nag_me import Nag
from auto_nag.round_robin import RoundRobin


class ToTriage(BzCleaner, Nag):
    def __init__(self):
        super(ToTriage, self).__init__()
        self.escalation = Escalation(self.people, data=self.get_config("escalation"))
        self.round_robin = RoundRobin.get_instance(teams=self.get_config("teams", []))
        self.components = self.round_robin.get_components()
        for person in self.get_config("persons", []):
            self.components += utils.get_triage_owners()[person]

    def description(self):
        return "Bugs to triage"

    def nag_template(self):
        return self.template()

    def has_default_product(self):
        return False

    def has_product_component(self):
        return True

    def ignore_meta(self):
        return True

    def columns(self):
        return ["component", "id", "summary", "type"]

    def columns_nag(self):
        return self.columns()

    def handle_bug(self, bug, data):
        # check if the product::component is in the list
        if not utils.check_product_component(self.components, bug):
            return None

        bugid = str(bug["id"])
        data[bugid] = {"type": bug["type"]}
        return bug

    def set_people_to_nag(self, bug, buginfo):
        priority = "default"
        if not self.filter_bug(priority):
            return None

        buginfo["type"] = bug["type"]
        fallback = self.round_robin.get_fallback(bug)

        owners = self.round_robin.get(bug, self.date, only_one=False, has_nick=False)
        real_owner = bug["triage_owner"]
        self.add_triage_owner(owners, real_owner=real_owner)
        if not self.add(owners, buginfo, priority=priority, fallback=fallback):
            self.add_no_manager(buginfo["id"])
        return bug

    def get_bz_params(self, date):
        self.date = lmdutils.get_date_ymd(date)
        prods, comps = utils.get_products_components(self.components)
        fields = ["triage_owner", "type"]
        params = {
            "include_fields": fields,
            "product": list(prods),
            "component": list(comps),
            "email1": "intermittent-bug-filer@mozilla.bugs",
            "email2": "wptsync@mozilla.bugs",
            "emailreporter1": 1,
            "emailreporter2": 1,
            "emailtype1": "notequals",
            "emailtype2": "notequals",
            "f1": "component",
            "f2": "OP",
            "f3": "cf_status_firefox_nightly",
            "f4": "cf_status_firefox_beta",
            "f5": "cf_status_firefox_release",
            "f6": "cf_status_firefox_esr",
            "f7": "bug_type",
            "f8": "CP",
            "f9": "bug_severity",
            "j_top": "OR",
            "limit": "0",
            "o1": "equals",
            "o3": "equals",
            "o4": "equals",
            "o5": "equals",
            "o6": "equals",
            "o7": "equals",
            "o9": "equals",
            "resolution": "---",
            "v1": "untriaged",
            "v3": "---",
            "v4": "---",
            "v5": "---",
            "v6": "---",
            "v7": "defect",
            "v9": "--"
        }

        return params


if __name__ == "__main__":
    ToTriage().run()
