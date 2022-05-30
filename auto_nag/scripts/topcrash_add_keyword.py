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
SIGNATURES_PAT = re.compile(r"\[@ ?(.*?) ?\]")


class TopcrashAddKeyword(BzCleaner):
    def description(self):
        return "Bugs with topcrash keyword but incorrect severity"

    def columns(self):
        return ["id", "summary", "severity", "added_keyword"]

    @staticmethod
    def __get_mail_to_ni(bug):
        for field in ["assigned_to", "triage_owner"]:
            person = bug.get(field, "")
            if not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        if bugid in data:
            return

        has_topcrash_keyword = "topcrash" in bug["keywords"]
        has_startup_keyword = "topcrash-startup" in bug["keywords"]
        if has_topcrash_keyword and has_startup_keyword:
            return

        signatures = SIGNATURES_PAT.findall(bug["cf_crash_signature"])
        has_topcrash_signature = any(
            signature in self.topcrashes for signature in signatures
        )
        assert has_topcrash_signature

        has_startup_signature = any(
            self.topcrashes.get(signature) for signature in signatures
        )

        should_add_keyword = (
            has_topcrash_signature
            and not (has_topcrash_keyword or has_startup_signature)
        ) or (has_startup_signature and not has_startup_keyword)

        if not should_add_keyword:
            return

        keyword_to_add = "topcrash-startup" if has_startup_signature else "topcrash"

        autofix = {
            "keywords": {
                "add": keyword_to_add,
            },
            "comment": {
                "body": "The bug is linked to a startup topcrash signature."
                if has_startup_signature
                else "The bug is linked to a topcrash signature.",
            },
        }

        ni_person = self.__get_mail_to_ni(bug)
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
            "added_keyword": keyword_to_add,
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
            "keywords": ["topcrash", "topcrash-startup"],
            "keywords_type": "nowords",
            "n1": 1,
            "f1": "longdesc",
            "o1": "casesubstring",
            "v1": "could you consider increasing the severity of this top-crash bug?",
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