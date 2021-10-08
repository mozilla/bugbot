# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import dateutil.parser
from libmozdata.bugzilla import Bugzilla, BugzillaUser

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class RegressionWithoutRegressedBy(BzCleaner):
    def description(self):
        return "Regressions without regressed_by and some dependencies"

    def handle_bug(self, bug, data):
        bugid = bug["id"]
        deps = set(bug["blocks"]) | set(bug["depends_on"])
        assignee = bug["assigned_to_detail"]
        if utils.is_no_assignee(assignee["email"]):
            assignee = None

        data[str(bugid)] = {
            "deps": deps,
            "assignee": assignee,
            "creator": bug["creator_detail"],
            "creation": dateutil.parser.parse(bug["creation_time"]),
            "has_regression_range": bug["cf_has_regression_range"] == "yes",
        }
        return bug

    def filter_bugs(self, bugs):
        all_deps = set()
        deps_to_max_allowed_date = {}

        for bugid, info in bugs.items():
            bugid = int(bugid)
            # we just keep bugs from dependencies created before bugid
            # since the others cannot be a regresser !
            info["deps"] = deps = set(x for x in info["deps"] if x < bugid)
            if deps:
                all_deps |= deps
                for dep in deps:
                    deps_to_max_allowed_date[dep] = info["creation"]

        def bug_handler(bug, data):
            if "meta" in bug["keywords"] or not bug["cf_last_resolved"]:
                data.add(bug["id"])

        def history_handler(bug, data):
            bugid = bug["id"]
            treated.add(bugid)
            resolved_before = False
            for h in bug["history"]:
                if resolved_before:
                    break
                for change in h["changes"]:
                    if change["field_name"] == "cf_last_resolved" and change["added"]:
                        date = dateutil.parser.parse(change["added"])
                        if date < deps_to_max_allowed_date[bugid]:
                            resolved_before = True
                            break
            if not resolved_before:
                data.add(bugid)

        invalids = set()
        treated = set()
        Bugzilla(
            bugids=list(all_deps),
            include_fields=["id", "keywords", "cf_last_resolved"],
            bughandler=bug_handler,
            bugdata=invalids,
            historyhandler=history_handler,
            historydata=invalids,
        ).get_data().wait()

        # Some bugs aren't accessible so they won't appear in treated (all_deps - treated)
        # Since we don't have any info about them, then we consider them as invalid
        invalids |= all_deps - treated

        for bugid, info in bugs.items():
            info["deps"] -= invalids

        bugs = {
            bugid: info
            for bugid, info in bugs.items()
            if info["deps"] or info["has_regression_range"]
        }

        return bugs

    def set_autofix(self, bugs):
        def history_handler(bug, data):
            bugid = str(bug["id"])
            deps = data[bugid]["deps"]
            stats = {}
            for h in bug["history"]:
                for change in h["changes"]:
                    if (
                        change["field_name"] in {"blocks", "depends_on"}
                        and change["added"] in deps
                    ) or change["field_name"] == "cf_has_regression_range":
                        who = h["who"]
                        stats[who] = stats.get(who, 0) + 1

            data[bugid]["winner"] = (
                max(stats.items(), key=lambda p: p[1])[0] if stats else None
            )

        no_assignee = [bugid for bugid, info in bugs.items() if not info["assignee"]]
        Bugzilla(
            bugids=no_assignee, historyhandler=history_handler, historydata=bugs
        ).get_data().wait()

        no_nick = {}
        for bugid, info in bugs.items():
            if info["assignee"]:
                winner = {
                    "mail": info["assignee"]["email"],
                    "nickname": info["assignee"]["nick"],
                }
                self.add_auto_ni(bugid, winner)
            elif info["winner"]:
                winner = info["winner"]
                if winner not in no_nick:
                    no_nick[winner] = []
                no_nick[winner].append(bugid)
            else:
                winner = {
                    "mail": info["creator"]["email"],
                    "nickname": info["creator"]["nick"],
                }
                self.add_auto_ni(bugid, winner)

        if no_nick:

            def user_handler(user, data):
                data[user["name"]] = user["nick"]

            data = {}
            BugzillaUser(
                user_names=list(no_nick.keys()),
                include_fields=["name", "nick"],
                user_handler=user_handler,
                user_data=data,
            ).wait()

            for bzmail, bugids in no_nick.items():
                nick = data[bzmail]
                for bugid in bugids:
                    self.add_auto_ni(bugid, {"mail": bzmail, "nickname": nick})

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        fields = [
            "blocks",
            "depends_on",
            "assigned_to",
            "creator",
            "creation_time",
            "cf_has_regression_range",
        ]
        reporter_skiplist = self.get_config("reporter_skiplist", default=[])
        reporter_skiplist = ",".join(reporter_skiplist)
        params = {
            "include_fields": fields,
            "bug_status": "__open__",
            "j1": "OR",
            "f1": "OP",
            "f2": "cf_has_regression_range",
            "o2": "equals",
            "v2": "yes",
            "j3": "AND",
            "f3": "OP",
            "f4": "keywords",
            "o4": "casesubstring",
            "v4": "regression",
            "j5": "OR",
            "f5": "OP",
            "f6": "blocked",
            "o6": "isnotempty",
            "f7": "dependson",
            "o7": "isnotempty",
            "f8": "CP",
            "f9": "CP",
            "f10": "CP",
            "f11": "regressed_by",
            "o11": "isempty",
            "n12": 1,
            "f12": "regressed_by",
            "o12": "changedafter",
            "v12": "1970-01-01",
            "f13": "creation_ts",
            "o13": "greaterthan",
            "v13": start_date,
            "f14": "keywords",
            "o14": "nowords",
            "v14": "regressionwindow-wanted",
            "f15": "reporter",
            "o15": "nowords",
            "v15": reporter_skiplist,
            "n16": 1,
            "f16": "longdesc",
            "o16": "casesubstring",
            "v16": "since this bug is a regression, could you fill (if possible) the regressed_by field",
        }

        return params

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(RegressionWithoutRegressedBy, self).get_bugs(
            date=date, bug_ids=bug_ids
        )
        bugs = self.filter_bugs(bugs)
        self.set_autofix(bugs)

        return bugs


if __name__ == "__main__":
    RegressionWithoutRegressedBy().run()
