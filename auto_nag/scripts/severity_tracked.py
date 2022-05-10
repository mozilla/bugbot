# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner

# TODO: should be moved when resolving https://github.com/mozilla/relman-auto-nag/issues/1384
LOW_SEVERITY = ["S3", "normal", "S4", "minor", "trivial", "enhancement"]


class SeverityTracked(BzCleaner):
    def __init__(self):
        super(SeverityTracked, self).__init__()
        if not self.init_versions():
            return

        self.nightly = self.versions["central"]
        self.beta = self.versions["beta"]
        self.release = self.versions["release"]
        self.tracking_nightly = utils.get_flag(self.nightly, "tracking", "central")
        self.tracking_beta = utils.get_flag(self.beta, "tracking", "beta")
        self.tracking_release = utils.get_flag(self.release, "tracking", "release")
        self.flags_map = {
            self.tracking_nightly: f"firefox{self.nightly} (nightly)",
            self.tracking_beta: f"firefox{self.beta} (beta)",
            self.tracking_release: f"firefox{self.release} (release)",
        }

    def description(self):
        return "Bugs with low severity that are marked as blocking or are tracked by release managers"

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        reasons = [
            ("tracked for " if bug[flag] == "+" else "blocking ") + self.flags_map[flag]
            for flag in self.flags_map.keys()
            if flag in bug and bug[flag] in ["blocking", "+"]
        ]

        data[bugid] = {
            "severity": bug["severity"],
            "reasons": reasons,
            "reasons_inline": utils.english_list(reasons),
        }
        self.extra_ni = data

        return bug

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "severity", "reasons"]

    def get_mail_to_auto_ni(self, bug):
        for field in ["assigned_to", "triage_owner"]:
            person = bug.get(field, "")
            if person and not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None

    def get_bz_params(self, date):
        fields = [
            "triage_owner",
            "assigned_to",
            "severity",
        ] + list(self.flags_map.keys())

        target_tracking = ["blocking", "+"]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "bug_severity": LOW_SEVERITY,
            "j1": "OR",
            "f1": "OP",
            "f2": self.tracking_nightly,
            "o2": "anyexact",
            "v2": target_tracking,
            "f3": self.tracking_beta,
            "o3": "anyexact",
            "v3": target_tracking,
            "f4": self.tracking_release,
            "o4": "anyexact",
            "v4": target_tracking,
            "f5": "CP",
            "n6": 1,
            "f6": "longdesc",
            "o6": "casesubstring",
            "v6": "could you consider increasing the severity of this tracked bug?",
            "f7": "keywords",
            "o7": "nowords",
            "v7": "intermittent-failure",
            "f8": "status_whiteboard",
            "o8": "notsubstring",
            "v8": "[stockwell]",
            "f9": "short_desc",
            "o9": "notregexp",
            "v9": r"^Perma |Intermittent ",
        }

        return params


if __name__ == "__main__":
    SeverityTracked().run()
