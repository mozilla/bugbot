# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla

from bugbot.bzcleaner import BzCleaner


class WebcompatPlatformWithoutKeyword(BzCleaner):
    normal_changes_max = 200

    def description(self):
        return "Core bugs blocking webcompat knowledge base entries without webcompat:platform-bug"

    def filter_no_nag_keyword(self):
        return False

    def has_default_products(self):
        return False

    def handle_bug(self, bug, data):
        data[bug["id"]] = {"depends_on": set(bug.get("depends_on", []))}
        return bug

    def get_core_bugs(self, bugs):
        core_bugs = set()
        for bug_data in bugs.values():
            core_bugs |= bug_data.get("depends_on", set())

        def bug_handler(bug, data):
            if "webcompat:platform-bug" not in bug["keywords"]:
                data[bug["id"]] = bug

        core_bug_data = {}

        Bugzilla(
            bugids=list(core_bugs),
            include_fields=["id", "summary", "keywords"],
            bughandler=bug_handler,
            bugdata=core_bug_data,
        ).get_data().wait()

        return core_bug_data

    def get_autofix_change(self):
        return {
            "keywords": {"add": ["webcompat:platform-bug"]},
        }

    def get_bz_params(self, date):
        fields = [
            "id",
            "depends_on",
        ]
        params = {
            "include_fields": fields,
            "product": "Web Compatibility",
            "component": "Knowledge Base",
        }

        return params

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        bugs = self.get_core_bugs(bugs)
        return bugs


if __name__ == "__main__":
    WebcompatPlatformWithoutKeyword().run()
