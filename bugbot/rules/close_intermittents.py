# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.bzcleaner import BzCleaner
from bugbot.components import ComponentName, fetch_component_teams


class Intermittents(BzCleaner):
    normal_changes_max: int = 2100

    def __init__(self):
        super().__init__()
        self.component_teams = fetch_component_teams()

    def description(self):
        return "Intermittent test failure bugs unchanged in 21 days"

    def get_max_actions(self):
        limit_per_run = 2100
        limit_per_team = 42

        # Number of teams that have bugs to be autoclosed
        number_of_teams = len(self.quota_actions)

        return min([limit_per_run // number_of_teams, limit_per_team])

    def has_product_component(self):
        return True

    def columns(self):
        return ["product", "component", "id", "summary"]

    def get_bz_params(self, date):
        params = {
            "include_fields": ["_custom", "product", "component"],
            "n1": "1",
            "f1": "longdescs.count",
            "o1": "changedafter",
            "v1": "-3w",
            "f3": "flagtypes.name",
            "o3": "notequals",
            "v3": "needinfo?",
            "f4": "OP",
            "n4": "1",
            "f5": "bug_status",
            "o5": "changedto",
            "v5": "REOPENED",
            "f6": "bug_status",
            "o6": "changedafter",
            "v6": "-7d",
            "f7": "CP",
            "f8": "bug_severity",
            "o8": "notequals",
            "v8": "S1",
            "f9": "keywords",
            "o9": "allwords",
            "v9": "intermittent-failure",
            "f10": "keywords",
            "o10": "nowords",
            "v10": "test-verify-fail,test-disabled,topcrash",
            "j11": "OR",
            "f11": "OP",
            "f12": "blocked",
            "o12": "isempty",
            # We want to include bugs that are blocked by sm-defects-intermittent
            # since it is rooting all SpiderMonkey's intermittent failures.
            # See https://github.com/mozilla/bugbot/issues/2635
            "f13": "blocked",
            "o13": "equals",
            "v13": 1729503,
            "f14": "CP",
            "resolution": "---",
            "status_whiteboard_type": "notregexp",
            "status_whiteboard": "(test disabled|test-disabled|testdisabled)",
        }

        return params

    def handle_bug(self, bug, data):
        status_flags = {
            field: "wontfix"
            for field, value in bug.items()
            if field.startswith("cf_status_") and value in ("affected", "fix-optional")
        }

        autofix = {
            **status_flags,
            "status": "RESOLVED",
            "resolution": "INCOMPLETE",
            "keywords": {"remove": ["leave-open"]},
            "comment": {
                "body": f"https://wiki.mozilla.org/Bug_Triage#Intermittent_Test_Failure_Cleanup\n{self.get_documentation()}"
            },
        }

        team_name = self.component_teams[ComponentName.from_bug(bug)]

        self.add_prioritized_action(bug, quota_name=team_name, autofix=autofix)

        return bug


if __name__ == "__main__":
    Intermittents().run()
