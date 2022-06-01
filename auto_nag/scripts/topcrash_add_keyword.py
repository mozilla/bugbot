# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from libmozdata.bugzilla import Bugzilla
from libmozdata.connection import Connection

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.topcrash import Topcrash

# TODO: should be moved when resolving https://github.com/mozilla/relman-auto-nag/issues/1384
HIGH_SEVERITY = {"S1", "critical", "S2", "major"}

MAX_SIGNATURES_PER_QUERY = 30


class TopcrashAddKeyword(BzCleaner):
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

        if len(existing_keywords) == 2:
            # No topcrash keywords to add, the bug has them all
            return

        signatures = utils.get_signatures(bug["cf_crash_signature"])

        if any(
            # Is it a startup topcrash bug?
            signature in self.topcrashes and self.topcrashes[signature]["is_startup"]
            for signature in signatures
        ):
            keywords_to_add = {"topcrash", "topcrash-startup"}

        elif any(
            # Is it a topcrash bug?
            signature in self.topcrashes
            for signature in signatures
        ):
            keywords_to_add = {"topcrash"}

        else:
            raise Exception("The bug should have a topcrash signature.")

        keywords_to_add = keywords_to_add - existing_keywords
        if not keywords_to_add:
            return

        autofix = {
            "keywords": {
                "add": list(keywords_to_add),
            },
            "comment": {
                "body": "The bug is linked to a startup topcrash signature."
                if "topcrash-startup" in keywords_to_add
                else "The bug is linked to a topcrash signature.",
            },
        }

        ni_person = utils.get_mail_to_ni(bug)
        if ni_person and bug["severity"] not in HIGH_SEVERITY:
            autofix["flags"] = [
                {
                    "name": "needinfo",
                    "requestee": ni_person["mail"],
                    "status": "?",
                    "new": "true",
                }
            ]
            autofix["comment"]["body"] += (
                f'\n:{ ni_person["nickname"] },'
                "could you consider increasing the severity of this top-crash bug?"
            )

        autofix["comment"]["body"] += f"\n\n{ self.get_documentation() }\n"
        self.autofix_changes[bugid] = autofix

        data[bugid] = {
            "severity": bug["severity"],
            "added_keywords": utils.english_list(sorted(keywords_to_add)),
        }

        return bug

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        self.query_url = None
        timeout = self.get_config("bz_query_timeout")
        bugs = self.get_data()
        params_list = self.get_bz_params(date)

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

    def get_bz_params(self, date):
        self.topcrashes = Topcrash(
            minimum_crashes=50,
            minimum_startup_crashes=20,
        ).get_signatures(date)

        fields = [
            "triage_owner",
            "assigned_to",
            "severity",
            "keywords",
            "cf_crash_signature",
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
