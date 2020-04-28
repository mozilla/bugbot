# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner


class RegressionSetStatusFlags(BzCleaner):
    def __init__(self):
        super().__init__()
        self.init_versions()
        self.status_central = utils.get_flag(
            self.versions["central"], "status", "central"
        )
        self.status_beta = utils.get_flag(self.versions["beta"], "status", "beta")
        self.status_release = utils.get_flag(
            self.versions["release"], "status", "release"
        )
        self.status_changes = {}

    def description(self):
        return "Set release status flags based on info from the regressing bug"

    def get_bz_params(self, date):
        # XXX should perhaps look further back than one week, e.g. a month?
        start_date, _ = self.get_dates(date)
        fields = [
            "regressed_by",
            self.status_central,
            self.status_beta,
            self.status_release,
        ]

        return {
            "include_fields": fields,
            "f1": "creation_ts",
            "o1": "greaterthan",
            "v1": start_date,
            "f2": "regressed_by",
            "o2": "isnotempty",
            "f3": "cf_status_firefox_release",
            "o3": "nowords",
            "v3": "fixed,verified",
            "f4": "cf_status_firefox_beta",
            "o4": "equals",
            "v4": "---",
            "resolution": ["---", "FIXED"],
        }

    def handle_bug(self, bug, data):
        bugid = bug["id"]
        if len(bug["regressed_by"]) != 1:
            # either we don't have access to the regressor, or there's more than one, either way leave things alone
            return
        bug["regressed_by"] = bug["regressed_by"][0]
        data[str(bugid)] = bug

    def get_flags_from_regressing_bugs(self, bugs):
        def bug_handler(bug, data):
            data[bug["id"]] = bug

        bugids = {info["regressed_by"] for info in bugs.values()}
        if not bugids:
            return {}
        data = {}
        filtered_bugs = {}
        Bugzilla(
            bugids=list(bugids), bughandler=bug_handler, bugdata=data
        ).get_data().wait()

        for bugid, info in bugs.items():
            regressor = info["regressed_by"]
            assert regressor in data
            regression_versions = sorted(
                v
                for v in data[regressor]
                if v.startswith("cf_status_firefox")
                and data[regressor][v] in ("fixed", "verified")
            )
            if not regression_versions:
                # don't know what to do, ignore
                continue
            if regression_versions[0].startswith("cf_status_firefox_esr"):
                continue
            regressed_version = int(regression_versions[0][len("cf_status_firefox") :])
            if regressed_version < int(self.versions["release"]):
                # old regression, leave it alone
                continue
            self.status_changes[bugid] = {}
            for channel in ("release", "beta", "central"):
                v = int(self.versions[channel])
                info[channel] = info["cf_status_firefox%d" % v]
                if info["cf_status_firefox%d" % v] != "---":
                    # XXX maybe check for consistency?
                    continue
                if v < regressed_version:
                    self.status_changes[bugid]["cf_status_firefox%d" % v] = "unaffected"
                    info[channel] = "unaffected"
                else:
                    self.status_changes[bugid]["cf_status_firefox%d" % v] = "affected"
                    info[channel] = "affected"
                filtered_bugs[bugid] = info

        return filtered_bugs

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        bugs = self.get_flags_from_regressing_bugs(bugs)
        return bugs

    def get_autofix_change(self):
        return self.status_changes

    def columns(self):
        return ("id", "summary", "regressed_by", "central", "beta", "release")


if __name__ == "__main__":
    RegressionSetStatusFlags().run()
