# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils
from bugbot.bzcleaner import BzCleaner


class P2MergeDay(BzCleaner):
    def must_run(self, date):
        return utils.is_merge_day(date)

    def description(self):
        return "P2 bugs with an assignee on merge day"

    def has_product_component(self):
        return True

    def ignore_meta(self):
        return True

    def columns(self):
        return ["product", "component", "id", "summary"]

    def handle_bug(self, bug, data):
        # check if the product::component is in the list
        if not utils.check_product_component(self.components, bug):
            return None
        return bug

    def get_bz_params(self, date):
        self.components = utils.get_config("workflow", "components")
        params = {
            "component": utils.get_components(self.components),
            "resolution": "---",
            "f1": "priority",
            "o1": "equals",
            "v1": "P2",
        }

        utils.get_empty_assignees(params)

        return params

    def get_autofix_change(self):
        return {
            "comment": {
                "body": "Set the priority to P1 since today is the merge day.\nSee [What Do You Triage](https://firefox-source-docs.mozilla.org/bug-mgmt/guides/priority.html) for more information."
            },
            "priority": "P1",
        }


if __name__ == "__main__":
    P2MergeDay().run()
