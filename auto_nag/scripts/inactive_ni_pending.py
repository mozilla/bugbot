# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.user_activity import UserActivity


class InactiveNeedinfoPending(BzCleaner):
    def __init__(self):
        super(InactiveNeedinfoPending, self).__init__()

    def description(self):
        return "Bugs with needinfo pending on inactive people"

    def columns(self):
        return ["id", "summary", "inactive_ni", "inactive_ni_count"]

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        self.handle_inactive_requestee(bugs)

        # Resolving https://github.com/mozilla/relman-auto-nag/issues/1300 should clean this
        # including improve the wording in the template (i.e., "See the search query on Bugzilla").
        self.query_url = utils.get_bz_search_url({"bug_id": ",".join(bugs.keys())})

        return bugs

    def handle_inactive_requestee(self, bugs):
        requestee_bugs = {}
        for bugid, bug in bugs.items():
            for flag in bug["needinfo_flags"]:
                if "requestee" not in flag:
                    flag["requestee"] = ""

                if flag["requestee"] not in requestee_bugs:
                    requestee_bugs[flag["requestee"]] = [bugid]
                else:
                    requestee_bugs[flag["requestee"]].append(bugid)

        user_activity = UserActivity()
        inactive_users = user_activity.check_users(requestee_bugs.keys())
        selected_bugs = []
        for requestee, bugids in requestee_bugs.items():
            if requestee in inactive_users:
                selected_bugs.extend(bugids)

        for bugid in set(bugs.keys()) - set(selected_bugs):
            del bugs[bugid]

        for bug in bugs.values():
            bug["inactive_ni"] = [
                {
                    "id": flag["id"],
                    "requestee": flag["requestee"],
                    "requestee_status": user_activity.get_string_status(
                        inactive_users[flag["requestee"]]
                    ),
                }
                for flag in bug["needinfo_flags"]
                if flag["requestee"] in inactive_users
            ]
            bug["inactive_ni_count"] = len(bug["inactive_ni"])

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "needinfo_flags": [
                flag for flag in bug["flags"] if flag["name"] == "needinfo"
            ]
        }

        return bug

    def get_bz_params(self, date):
        fields = ["flags"]
        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "flagtypes.name",
            "o1": "equals",
            "v1": "needinfo?",
        }

        return params


if __name__ == "__main__":
    InactiveNeedinfoPending().run()
