# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from collections import defaultdict

from libmozdata.bugzilla import BugzillaProduct

from auto_nag.bzcleaner import BzCleaner
from auto_nag.components import ComponentName


class SeverityMigration(BzCleaner):
    """Drop old severities to let teams retriage them.

    TODO: This script is temporary; it should be removed once all old severities
    are dropped.
    """

    def __init__(self):
        super().__init__()
        self.component_team = self._get_component_team_mapping()

    def description(self):
        return "Bugs with old severities"

    def must_run(self, date):
        return date.weekday() == 0  # Monday

    def columns(self):
        return ["team_name", "id", "summary"]

    def _get_component_team_mapping(self):
        result = {}

        def handler(product, data):
            for component in product["components"]:
                data[ComponentName(product["name"], component["name"])] = component[
                    "team_name"
                ]

        BugzillaProduct(
            product_types="accessible",
            include_fields=[
                "name",
                "components.name",
                "components.team_name",
            ],
            product_handler=handler,
            product_data=result,
        ).wait()

        return result

    def handle_bug(self, bug, data):
        component_name = ComponentName(bug["product"], bug["component"])
        team_name = self.component_team[component_name]

        bugid = str(bug["id"])
        data[bugid] = {
            "team_name": team_name,
        }

        return bug

    def get_bugs(self, date="today", bug_ids=..., chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)

        team_bugs = defaultdict(list)
        for bug in bugs.values():
            team_bugs[bug["team_name"]].append(bug)

        bugs = {
            bug["id"]: bug
            for _bugs in team_bugs.values()
            for bug in sorted(_bugs, key=lambda x: x["id"], reverse=True)[:10]
        }

        return bugs

    def get_autofix_change(self):
        return {
            "keywords": {"remove": "triaged"},
            "severity": "--",
            "comment": {
                "body": "In the process of [migrating remaining bugs to the new severity system](https://bugzilla.mozilla.org/show_bug.cgi?id=1789259), the severity for this bug cannot be automatically determined. Please retriage this bug using the [new severity system](https://wiki.mozilla.org/BMO/UserGuide/BugFields#bug_severity).",
            },
        }

    def filter_no_nag_keyword(self):
        return False

    def ignore_meta(self):
        return False

    def has_access_to_sec_bugs(self):
        return True

    def get_products(self):
        products = super().get_products()
        products += ["Thunderbird", "Calendar", "Chat Core", "Mailnews Core"]
        return products

    def get_bz_params(self, date):
        params = {
            "include_fields": ["product", "component"],
            "resolution": "---",
            "bug_severity": {"blocker", "critical", "major"},
            "f1": "cf_crash_signature",
            "o1": "isempty",
            "f2": "product",
            "o2": "notequals",
            "v2": "Testing",
        }

        return params


if __name__ == "__main__":
    SeverityMigration().run()
