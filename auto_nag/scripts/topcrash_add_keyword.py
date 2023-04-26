# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools
import re
from collections import defaultdict
from typing import Dict, Iterable

from libmozdata.bugzilla import Bugzilla
from libmozdata.connection import Connection

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.constants import LOW_SEVERITY
from auto_nag.history import History
from auto_nag.topcrash import TOP_CRASH_IDENTIFICATION_CRITERIA, Topcrash

MAX_SIGNATURES_PER_QUERY = 30


class TopcrashAddKeyword(BzCleaner):
    def __init__(self):
        super().__init__()
        self.topcrashes = None
        self.topcrashes_restrictive = None

    def description(self):
        return "Bugs with missing topcrash keywords"

    def columns(self):
        return ["id", "summary", "severity", "added_keywords"]

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        if bugid in data:
            return

        existing_keywords = {
            keyword
            for keyword in ("topcrash", "topcrash-startup")
            if keyword in bug["keywords"]
        }

        top_crash_signatures = [
            signature
            for signature in utils.get_signatures(bug["cf_crash_signature"])
            if signature in self.topcrashes
        ]

        if not top_crash_signatures:
            raise Exception("The bug should have a topcrash signature.")

        elif any(
            # Is it a startup topcrash bug?
            any(criterion["is_startup"] for criterion in self.topcrashes[signature])
            for signature in top_crash_signatures
        ):
            keywords_to_add = {"topcrash", "topcrash-startup"}

        else:
            keywords_to_add = {"topcrash"}

        keywords_to_add = keywords_to_add - existing_keywords
        is_keywords_removed = utils.is_keywords_removed_by_autonag(bug, keywords_to_add)

        autofix = {
            "comment": {
                "body": "",
            },
        }

        if keywords_to_add and (
            not is_keywords_removed
            or self._is_matching_restrictive_criteria(top_crash_signatures)
        ):
            autofix["keywords"] = {
                "add": sorted(keywords_to_add),
            }
            autofix["comment"]["body"] += self.get_matching_criteria_comment(
                top_crash_signatures, is_keywords_removed
            )

        ni_person = utils.get_mail_to_ni(bug)
        if (
            ni_person
            and bug["severity"] in LOW_SEVERITY
            and "meta" not in bug["keywords"]
            and not is_keywords_removed
            and not self._has_severity_increase_comment(bug)
        ):
            autofix["flags"] = [
                {
                    "name": "needinfo",
                    "requestee": ni_person["mail"],
                    "status": "?",
                    "new": "true",
                }
            ]
            autofix["comment"]["body"] += (
                f'\n:{ ni_person["nickname"] }, '
                "could you consider increasing the severity of this top-crash bug?"
            )

        if not autofix["comment"]["body"]:
            # No comment, no action
            return

        autofix["comment"]["body"] += f"\n\n{ self.get_documentation() }\n"
        self.autofix_changes[bugid] = autofix

        data[bugid] = {
            "severity": bug["severity"],
            "added_keywords": (
                utils.english_list(autofix["keywords"]["add"])
                if "keywords" in autofix
                else "-"
            ),
        }

        return bug

    def get_matching_criteria_comment(
        self,
        signatures: list,
        is_keywords_removed: bool,
    ) -> str:
        """Generate a comment with the matching criteria for the given signatures.

        Args:
            signatures: The list of signatures to generate the comment for.
            is_keywords_removed: Whether the topcrash keywords was removed earlier.

        Returns:
            The comment for the matching criteria.
        """
        matching_criteria: Dict[str, bool] = defaultdict(bool)
        for signature in signatures:
            for criterion in self.topcrashes[signature]:
                matching_criteria[criterion["criterion_name"]] |= criterion[
                    "is_startup"
                ]

        introduction = (
            (
                "Sorry for removing the keyword earlier but there is a recent "
                "change in the ranking, so the bug is again linked to "
                if is_keywords_removed
                else "The bug is linked to "
            ),
            (
                "a topcrash signature, which matches "
                if len(signatures) == 1
                else "topcrash signatures, which match "
            ),
            "the following [",
            "criterion" if len(matching_criteria) == 1 else "criteria",
            "](https://wiki.mozilla.org/CrashKill/Topcrash):\n",
        )

        criteria = (
            " ".join(("-", criterion_name, "(startup)\n" if is_startup else "\n"))
            for criterion_name, is_startup in matching_criteria.items()
        )

        return "".join(itertools.chain(introduction, criteria))

    def _has_severity_increase_comment(self, bug):
        return any(
            "could you consider increasing the severity of this top-crash bug?"
            in comment["raw_text"]
            for comment in reversed(bug["comments"])
            if comment["creator"] == History.BOT
        )

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        self.query_url = None
        timeout = self.get_config("bz_query_timeout")
        bugs = self.get_data()
        params_list = self.get_bz_params_list(date)

        searches = [
            Bugzilla(
                params,
                bughandler=self.bughandler,
                bugdata=bugs,
                timeout=timeout,
            ).get_data()
            for params in params_list
        ]

        for search in searches:
            search.wait()

        return bugs

    def _is_matching_restrictive_criteria(self, signatures: Iterable) -> bool:
        topcrashes = self._get_restrictive_topcrash_signatures()
        return any(signature in topcrashes for signature in signatures)

    def _get_restrictive_topcrash_signatures(self) -> dict:
        if self.topcrashes_restrictive is None:
            restrictive_criteria = []
            for criterion in TOP_CRASH_IDENTIFICATION_CRITERIA:
                restrictive_criterion = {
                    **criterion,
                    "tc_limit": criterion["tc_limit"] // 2,
                }

                if "tc_limit_startup" in criterion:
                    restrictive_criterion["tc_limit_startup"] //= 2

                restrictive_criteria.append(restrictive_criterion)

            self.topcrashes_restrictive = Topcrash(
                criteria=restrictive_criteria
            ).get_signatures()

        return self.topcrashes_restrictive

    def get_bz_params_list(self, date):
        self.topcrashes = Topcrash(date).get_signatures()

        fields = [
            "triage_owner",
            "assigned_to",
            "severity",
            "keywords",
            "cf_crash_signature",
            "history",
            "comments.creator",
            "comments.raw_text",
        ]
        params_base = {
            "include_fields": fields,
            "resolution": "---",
        }
        self.amend_bzparams(params_base, [])

        params_list = []
        for signatures in Connection.chunks(
            list(self.topcrashes.keys()),
            MAX_SIGNATURES_PER_QUERY,
        ):
            params = params_base.copy()
            n = int(utils.get_last_field_num(params))
            params[f"f{n}"] = "OP"
            params[f"j{n}"] = "OR"
            for signature in signatures:
                n += 1
                params[f"f{n}"] = "cf_crash_signature"
                params[f"o{n}"] = "regexp"
                # Using `(@ |@)` instead of `@ ?` and ( \]|\]) instead of ` ?]`
                # is a workaround. Strangely `?` stays with the encoded form (%3F)
                # in Bugzilla query.
                # params[f"v{n}"] = f"\[@ ?{re.escape(signature)} ?\]"
                params[f"v{n}"] = rf"\[(@ |@){re.escape(signature)}( \]|\])"
            params[f"f{n+1}"] = "CP"
            params_list.append(params)

        return params_list


if __name__ == "__main__":
    TopcrashAddKeyword().run()
