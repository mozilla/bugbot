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
        self.status_esr = utils.get_flag(self.versions["esr_previous"], "status", "esr")
        self.status_esr_next = utils.get_flag(self.versions["esr"], "status", "esr")
        self.status_changes = {}

    def description(self):
        return "Set release status flags based on info from the regressing bug"

    def get_bz_params(self, date):
        # XXX should perhaps look further back than one week, e.g. a month?
        start_date, _ = self.get_dates(date)

        # Find all bugs with regressed_by information which were open after start_date or
        # whose regressed_by field was set after start_date.

        return {
            "include_fields": ["regressed_by", "_custom"],
            "f1": "OP",
            "j1": "OR",
            "f2": "creation_ts",
            "o2": "greaterthan",
            "v2": start_date,
            "f3": "regressed_by",
            "o3": "changedafter",
            "v3": start_date,
            "f4": "CP",
            "f5": "regressed_by",
            "o5": "isnotempty",
            "f6": "cf_status_firefox_release",
            "o6": "nowords",
            "v6": "fixed,verified",
            "resolution": ["---", "FIXED"],
        }

    def get_extra_for_template(self):
        if self.status_esr == self.status_esr_next:
            return [f"esr{self.versions['esr']}"]
        return [f"esr{self.versions['esr_previous']}", f"esr{self.versions['esr']}"]

    def handle_bug(self, bug, data):
        bugid = bug["id"]
        if len(bug["regressed_by"]) != 1:
            # either we don't have access to the regressor, or there's more than one, either way leave things alone
            return
        bug["regressed_by"] = bug["regressed_by"][0]
        data[str(bugid)] = bug

    def get_flags_from_regressing_bugs(self, bugids):
        def bug_handler(bug, data):
            data[bug["id"]] = bug

        data = {}
        Bugzilla(
            bugids=list(bugids), bughandler=bug_handler, bugdata=data
        ).get_data().wait()

        return data

    def get_status_changes(self, bugs):
        bugids = {info["regressed_by"] for info in bugs.values()}
        if not bugids:
            return {}

        data = self.get_flags_from_regressing_bugs(bugids)

        filtered_bugs = {}
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
                # shouldn't happen: esrXX sorts after YY
                continue
            regressed_version = int(regression_versions[0][len("cf_status_firefox") :])

            fixed_versions = sorted(
                v
                for v in info
                if v.startswith("cf_status_firefox")
                and info[v] in ("fixed", "verified")
            )
            if len(fixed_versions) > 0 and fixed_versions[0].startswith(
                "cf_status_firefox_esr"
            ):
                # shouldn't happen: esrXX sorts after YY
                continue
            fixed_version = (
                int(fixed_versions[0][len("cf_status_firefox") :])
                if len(fixed_versions) > 0
                else None
            )

            self.status_changes[bugid] = {}
            for channel in ("release", "beta", "central"):
                v = int(self.versions[channel])
                flag = utils.get_flag(v, "status", channel)
                info[channel] = info[flag]
                if info[flag] != "---":
                    # XXX maybe check for consistency?
                    continue
                if fixed_version is not None and v >= fixed_version:
                    # Bug was fixed in an earlier version, don't set the flag
                    continue
                if v >= regressed_version:
                    self.status_changes[bugid][flag] = "affected"
                    info[channel] = "affected"
                else:
                    self.status_changes[bugid][flag] = "unaffected"
                    info[channel] = "unaffected"
                filtered_bugs[bugid] = info

            esr_versions = set([self.versions["esr"], self.versions["esr_previous"]])
            for v in esr_versions:
                info.setdefault("esr", {})
                flag = utils.get_flag(v, "status", "esr")
                info["esr"][f"esr{v}"] = info[flag]
                if info[flag] != "---":
                    # XXX maybe check for consistency?
                    continue
                if fixed_version is not None and int(v) >= fixed_version:
                    # Bug was fixed in an earlier version, don't set the flag
                    continue
                if data[regressor].get(flag) in ("fixed", "verified"):
                    # regressor was uplifted, so the regression affects this branch
                    self.status_changes[bugid][flag] = "affected"
                    info["esr"][f"esr{v}"] = "affected"
                elif int(v) >= regressed_version:
                    # regression from before this branch, also affected
                    self.status_changes[bugid][flag] = "affected"
                    info["esr"][f"esr{v}"] = "affected"
                else:
                    self.status_changes[bugid][flag] = "unaffected"
                    info["esr"][f"esr{v}"] = "unaffected"
                filtered_bugs[bugid] = info

        for bugid in filtered_bugs:
            regressor = bugs[bugid]["regressed_by"]
            self.status_changes[bugid]["comment"] = {
                "body": f"{self.description()} {regressor}",
                # if the regressing bug is private (security or otherwise
                # confidential), don't leak its number through our comment (the
                # regressed_by field is not public in that case)
                "is_private": bool(data[regressor].get("groups")),
            }

        return filtered_bugs

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        bugs = self.get_status_changes(bugs)
        return bugs

    def get_autofix_change(self):
        return self.status_changes

    def columns(self):
        return ["id", "summary", "regressed_by", "central", "beta", "release", "esr"]


if __name__ == "__main__":
    RegressionSetStatusFlags().run()
