# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from libmozdata.bugzilla import Bugzilla

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner

VERSION_PREFIX = "cf_status_firefox"
N = len(VERSION_PREFIX)


class AffectedFlagConfirm(BzCleaner):
    def description(self):
        return "Unconfirmed bugs that have an affected Firefox version flag"

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {"creator": bug["creator"]}
        return bug

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        self.query_url = None

        def history_handler(bug, data):

            bugid = str(bug["id"])
            creator = data[bugid]["creator"]
            removed_status = set()
            for event in reversed(bug["history"]):

                affected_version = ""
                for change in event["changes"]:
                    if (
                        change["field_name"].startswith(VERSION_PREFIX)
                        and change["field_name"] not in removed_status
                    ):
                        if change["added"] == "affected":
                            if event["who"] != creator:
                                affected_version = change["field_name"][N:]
                                break
                        elif change["removed"] == "affected":
                            removed_status.add(change["field_name"])

                if affected_version:
                    data[bugid]["affected_version"] = affected_version
                    break

        Bugzilla(
            list(bugs.keys()),
            historyhandler=history_handler,
            historydata=bugs,
            timeout=960,
        ).get_data().wait()

        return {bugid: bug for bugid, bug in bugs.items() if "affected_version" in bug}

    def get_bz_params(self, date):
        fields = ["creator"]
        params = {
            "include_fields": fields,
            "bug_status": "UNCONFIRMED",
            "j1": "OR",
            "f1": "OP",
        }

        last_version = utils.get_nightly_version_from_bz()
        first_version = last_version - 40
        for version in range(first_version, last_version + 1):
            i = version - first_version + 2
            params[f"f{i}"] = f"cf_status_firefox{version}"
            params[f"o{i}"] = "equals"
            params[f"v{i}"] = "affected"
        params[f"f{i+1}"] = "CP"

        return params

    def get_autofix_change(self):
        return {
            "comment": {
                "body": "The bug has an affected Firefox version flag, thus the bug will be considered confirmed."
            },
            "status": "NEW",
        }


if __name__ == "__main__":
    AffectedFlagConfirm().run()
