# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner


class assigneeButUnconfirmed(BzCleaner):
    def __init__(self):
        super(assigneeButUnconfirmed, self).__init__()

    def description(self):
        return "Get unconfirmed bugs with assignee"

    def get_bz_params(self, date):
        params = {
            "resolution": "---",
            "bug_status": "UNCONFIRMED",
            "emailtype1": "notequals",
            "email1": "nobody@mozilla.org",
            "emailassigned_to1": "1",
            "emailtype2": "notregexp",
            "email2": ".*@.*.bugs",
            "emailassigned_to2": "1",
        }
        return params

    def get_autofix_change(self):
        return {"bug_status": "ASSIGNED"}


if __name__ == "__main__":
    assigneeButUnconfirmed().run()
