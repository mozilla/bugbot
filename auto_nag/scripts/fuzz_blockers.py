# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag.nag_me import Nag


class FuzzBlockers(BzCleaner, Nag):
    def description(self):
        return "Bugs that prevent fuzzing from making progress"

    def nag_template(self):
        return super().template()

    def set_people_to_nag(self, bug, buginfo):
        persons = [
            bug["assigned_to"],
            bug["triage_owner"],
        ]
        if not self.add(persons, buginfo):
            self.add_no_manager(buginfo["id"])

        return bug

    def get_bz_params(self, date):
        fields = [
            "triage_owner",
            "assigned_to",
        ]
        return {
            "include_fields": fields,
            "bug_status": ["UNCONFIRMED", "NEW", "ASSIGNED", "REOPENED"],
            "f1": "status_whiteboard",
            "o1": "substring",
            "v1": "[fuzzblocker]",
        }


if __name__ == "__main__":
    FuzzBlockers().run()
