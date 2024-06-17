# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Dict

from libmozdata import utils as lmdutils

from bugbot import utils
from bugbot.bzcleaner import BzCleaner
from bugbot.constants import HIGH_SEVERITY, SECURITY_KEYWORDS
from bugbot.history import History
from bugbot.topcrash import TOP_CRASH_IDENTIFICATION_CRITERIA, Topcrash

MAX_SIGNATURES_PER_QUERY = 30


class CrashSmallVolume(BzCleaner):
    def __init__(
        self,
        min_crash_volume: int = 15,
        oldest_severity_change_days: int = 30,
        oldest_topcrash_added_days: int = 21,
    ):
        """Constructor.

        Args:
            min_crash_volume: the minimum number of crashes per week for a
                signature to not be considered low volume.
            oldest_severity_change_days: if the bug severity has been changed by
                a human or bugbot in the last X days, we will not downgrade the
                severity to `S3`.
            oldest_topcrash_added_days: if the bug has been marked as topcrash
                in the last X days, we will ignore it.
        """
        super().__init__()

        self.min_crash_volume = min_crash_volume
        topcrash = Topcrash(
            criteria=self._adjust_topcrash_criteria(TOP_CRASH_IDENTIFICATION_CRITERIA)
        )
        assert (
            topcrash.min_crashes >= min_crash_volume
        ), "min_crash_volume should not be higher than the min_crashes used for the topcrash criteria"

        self.topcrash_signatures = topcrash.get_signatures()
        self.blocked_signatures = topcrash.get_blocked_signatures()
        self.oldest_severity_change_date = lmdutils.get_date(
            "today", oldest_severity_change_days
        )
        self.oldest_topcrash_added_date = lmdutils.get_date(
            "today", oldest_topcrash_added_days
        )

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

        if self._is_topcrash_recently_added(bug):
            return None

        signatures = utils.get_signatures(bug["cf_crash_signature"])

        if any(signature in self.blocked_signatures for signature in signatures):
            # Ignore those bugs as we can't be sure.
            return None

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

        data[bugid] = {
            "severity": bug["severity"],
            "ignore_severity": (
                bug["severity"] not in HIGH_SEVERITY
                or bug["groups"] == "security"
                or any(keyword in SECURITY_KEYWORDS for keyword in bug["keywords"])
                or "[fuzzblocker]" in bug["whiteboard"]
                or self._is_severity_recently_changed_by_human_or_bugbot(bug)
                or self._has_severity_downgrade_comment(bug)
            ),
            "keywords_to_remove": keywords_to_remove,
            "signatures": signatures,
            "needinfos_to_remove": (
                self.get_needinfo_topcrash_ids(bug)
                if "topcrash" in keywords_to_remove
                else []
            ),
        }

        return bug

    def _get_low_volume_crash_signatures(self, bugs: Dict[str, dict]) -> set:
        """From the provided bugs, return the list of signatures that have a
        low crash volume.
        """

        signatures = {
            signature
            for bug in bugs.values()
            if not bug["ignore_severity"]
            for signature in bug["signatures"]
        }

        if not signatures:
            return set()

        signature_volume = Topcrash().fetch_signature_volume(signatures)

        low_volume_signatures = {
            signature
            for signature, volume in signature_volume.items()
            if volume < self.min_crash_volume
        }

        return low_volume_signatures

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
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
                autofix["flags"] = [
                    {
                        "id": flag_id,
                        "status": "X",
                    }
                    for flag_id in bug["needinfos_to_remove"]
                ]

            if not bug["ignore_severity"] and all(
                signature in low_volume_signatures for signature in bug["signatures"]
            ):
                reasons.append(
                    f"Since the crash volume is low (less than {self.min_crash_volume} per week), "
                    "the severity is downgraded to `S3`. "
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

    def get_needinfo_topcrash_ids(self, bug: dict) -> list[int]:
        """Get the IDs of the needinfo flags requested by the bot regarding increasing the severity."""
        needinfo_flags = [
            flag
            for flag in bug.get("flags", [])
            if flag["name"] == "needinfo" and flag["requestee"] == History.BOT
        ]

        needinfo_comment = (
            "could you consider increasing the severity of this top-crash bug?"
        )

        severity_comment_times = [
            comment["creation_time"]
            for comment in bug["comments"]
            if comment["creator"] == History.BOT
            and needinfo_comment in comment["raw_text"]
        ]

        return [
            flag["id"]
            for flag in needinfo_flags
            if flag["creation_date"] in severity_comment_times
        ]

    @staticmethod
    def _has_severity_downgrade_comment(bug):
        for comment in reversed(bug["comments"]):
            if (
                comment["creator"] == History.BOT
                and "the severity is downgraded to" in comment["raw_text"]
            ):
                return True
        return False

    def _is_topcrash_recently_added(self, bug: dict):
        """Return True if the topcrash keyword was added recently."""

        for entry in reversed(bug["history"]):
            if entry["when"] < self.oldest_topcrash_added_date:
                break

            for change in entry["changes"]:
                if change["field_name"] == "keywords" and "topcrash" in change["added"]:
                    return True

        return False

    def _is_severity_recently_changed_by_human_or_bugbot(self, bug):
        for entry in reversed(bug["history"]):
            if entry["when"] < self.oldest_severity_change_date:
                break

            # We ignore bot changes except for bugbot
            if utils.is_bot_email(entry["who"]) and entry["who"] not in (
                "autonag-nomail-bot@mozilla.tld",
                "release-mgmt-account-bot@mozilla.tld",
            ):
                continue

            if any(change["field_name"] == "severity" for change in entry["changes"]):
                return True

        return False

    def get_bz_params(self, date):
        fields = [
            "severity",
            "keywords",
            "whiteboard",
            "cf_crash_signature",
            "comments.raw_text",
            "comments.creator",
            "comments.creation_time",
            "history",
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
            "f6": "cf_crash_signature",
            "o6": "isnotempty",
            "f7": "CP",
            "f8": "CP",
            "f9": "creation_ts",
            "o9": "lessthan",
            "v9": "-1w",
        }

        return params


if __name__ == "__main__":
    CrashSmallVolume().run()
