# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.topcrash import TOP_CRASH_IDENTIFICATION_CRITERIA, Topcrash

# TODO: should be moved when resolving https://github.com/mozilla/relman-auto-nag/issues/1384
HIGH_SEVERITY = {"S1", "critical", "S2", "major"}

MAX_SIGNATURES_PER_QUERY = 30


class CrashSmallVolume(BzCleaner):
    def __init__(self):
        super().__init__()

        topcrash = Topcrash(
            criteria=self._adjust_topcrash_criteria(TOP_CRASH_IDENTIFICATION_CRITERIA)
        )
        self.topcrash_signatures = topcrash.get_signatures()
        self.blocked_signatures = topcrash.get_blocked_signatures()

    def description(self):
        return "Bugs with small crash volume"

    def columns(self):
        return ["id", "summary", "severity", "deleted_keywords_count"]

    def _get_last_topcrash_added(self, bug):
        pass

    def _adjust_topcrash_criteria(self, topcrash_criteria):
        factor = 2
        new_criteria = []
        for criterion in topcrash_criteria:
            criterion = {
                **criterion,
                "tc_limit": criterion["tc_limit"] * factor,
            }
            if "tc_startup_limit" in criterion:
                criterion["tc_startup_limit"] = criterion["tc_startup_limit"] * factor

            new_criteria.append(criterion)

        return new_criteria

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        signatures = utils.get_signatures(bug["cf_crash_signature"])

        top_crash_signatures = [
            signature
            for signature in signatures
            if signature in self.topcrash_signatures
        ]

        keep_topcrash_startup = any(
            any(
                criterion["is_startup"]
                for criterion in self.topcrash_signatures[signature]
            )
            for signature in top_crash_signatures
        )

        keywords_to_remove = None
        if not top_crash_signatures:
            keywords_to_remove = set(bug["keywords"]) & {"topcrash", "topcrash-startup"}
        elif not keep_topcrash_startup:
            keywords_to_remove = set(bug["keywords"]) & {"topcrash-startup"}
        else:
            return None

        is_security = bug["groups"] == "security" or any(
            keyword.startswith("sec-") for keyword in bug["keywords"]
        )

        data[bugid] = {
            "severity": bug["severity"],
            "is_security": is_security,
            "keywords_to_remove": keywords_to_remove,
            "signatures": signatures,
        }

        return bug

    def _get_low_volume_crash_signatures(self, bugs):
        signatures = {
            signature
            for bug in bugs.values()
            if not bug["is_security"] and bug["severity"] in HIGH_SEVERITY
            for signature in bug["signatures"]
        }

        signature_volume = Topcrash().fetch_signature_volume(signatures)

        low_volume_signatures = {
            signature for signature, volume in signature_volume.items() if volume < 5
        }

        return low_volume_signatures

    def get_bugs(self, date="today", bug_ids=..., chunk_size=None):
        bugs = super().get_bugs(date, bug_ids, chunk_size)
        self.set_autofix(bugs)

        # Keep only bugs with an autofix
        bugs = {
            bugid: bug for bugid, bug in bugs.items() if bugid in self.autofix_changes
        }

        return bugs

    def set_autofix(self, bugs):
        """Set the autofix for each bug."""

        low_volume_signatures = self._get_low_volume_crash_signatures(bugs)

        for bugid, bug in bugs.items():
            autofix = {}
            reasons = []
            if bug["keywords_to_remove"]:
                reasons.append(
                    "Based on the [topcrash criteria](https://wiki.mozilla.org/CrashKill/Topcrash), the crash "
                    + (
                        "signature linked to this bug is not a topcrash signature anymore."
                        if len(bug["signatures"]) == 1
                        else "signatures linked to this bug are not in the topcrash signatures anymore."
                    )
                )
                autofix["keywords"] = {"remove": list(bug["keywords_to_remove"])}

            if (
                not bug["is_security"]
                and bug["severity"] in HIGH_SEVERITY
                and all(
                    signature in low_volume_signatures
                    or signature in self.blocked_signatures
                    for signature in bug["signatures"]
                )
            ):
                reasons.append(
                    "Since the crash volume is very low, the severity is downgraded to `S3`. "
                    "Feel free to change it back if you think the bug is still critical."
                )
                autofix["severity"] = "S3"
                bug["severity"] += " → " + autofix["severity"]

            if autofix:

                bug["deleted_keywords_count"] = (
                    len(bug["keywords_to_remove"]) if bug["keywords_to_remove"] else "-"
                )
                reasons.append(self.get_documentation())
                autofix["comment"] = {
                    "body": "\n\n".join(reasons),
                }
                self.autofix_changes[bugid] = autofix

    def get_bz_params(self, date):
        fields = [
            "severity",
            "keywords",
            "cf_crash_signature",
        ]
        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "OP",
            "j1": "OR",
            "f2": "keywords",
            "o2": "anywords",
            "v2": ["topcrash", "topcrash-startup"],
            "f3": "OP",
            "j3": "AND",
            "f4": "bug_severity",
            "o4": "anyexact",
            "v4": list(HIGH_SEVERITY),
            "n5": "1",
            "f5": "bug_severity",
            "o5": "changedafter",
            "v5": "-30d",
            "f6": "cf_crash_signature",
            "o6": "isnotempty",
            "f7": "CP",
            "f8": "CP",
        }

        return params


if __name__ == "__main__":
    CrashSmallVolume().run()
