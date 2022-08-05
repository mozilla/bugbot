# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
from typing import Dict

import requests
from libmozdata.bugzilla import Bugzilla

from auto_nag import logger, utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.people import People
from auto_nag.user_activity import UserActivity, UserStatus

PUSHLOG_PAT = re.compile(r"Pushlog: (.+)")
BUG_PAT = re.compile(r"[\t ]*[Bb][Uu][Gg][\t ]*([0-9]+)")


def is_ignorable_path(path: str) -> bool:
    # TODO: also ignore other kinds of files that certainly can't cause regressions.

    if any(
        path.endswith(ext) for ext in (".txt", ".md", ".rst", ".pdf", ".doc", ".otf")
    ):
        return True

    # This code was adapted from https://github.com/mozsearch/mozsearch/blob/2e24a308bf66b4c149683bfeb4ceeea3b250009a/router/router.py#L127
    if (
        "/test/" in path
        or "/tests/" in path
        or "/mochitest/" in path
        or "/unit/" in path
        or "/gtest/" in path
        or "testing/" in path
        or "/jsapi-tests/" in path
        or "/reftests/" in path
        or "/reftest/" in path
        or "/crashtests/" in path
        or "/crashtest/" in path
        or "/gtests/" in path
        or "/googletest/" in path
    ):
        return True

    return False


class FuzzingBisectionWithoutRegressedBy(BzCleaner):
    def __init__(self, max_ni: int = 3) -> None:
        """Constructor

        Args:
            max_ni: The maximum number of regression authors to needinfo. If the
                number of authors exceeds the limit no one will be needinfo'ed.
        """
        super().__init__()
        self.people = People.get_instance()
        self.autofix_regressed_by: Dict[str, str] = {}
        self.max_ni = max_ni

    def description(self):
        return "Bugs with a fuzzing bisection and without regressed_by"

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "assigned_to": bug["assigned_to"],
        }
        return bug

    def set_autofix(self, bugs):
        ni_template = self.get_needinfo_template()
        docs = self.get_documentation()

        for bug_id, bug in bugs.items():
            if "regressor_bug_id" in bug:
                self.autofix_regressed_by[bug_id] = {
                    "comment": {
                        "body": "Setting regressed_by field after analyzing regression range found by bugmon."
                    },
                    "regressed_by": {"add": [bug["regressor_bug_id"]]},
                }
            elif "needinfo_targets" in bug:
                nicknames = [":" + user["nickname"] for user in bug["needinfo_targets"]]
                ni_comment = ni_template.render(
                    nicknames=utils.english_list(nicknames),
                    authors_count=len(nicknames),
                    is_assignee=not utils.is_no_assignee(bug["assigned_to"]),
                    plural=utils.plural,
                    documentation=docs,
                )
                ni_flags = [
                    {
                        "name": "needinfo",
                        "requestee": user["mail"],
                        "status": "?",
                        "new": "true",
                    }
                    for user in bug["needinfo_targets"]
                ]
                self.autofix_regressed_by[bug_id] = {
                    "flags": ni_flags,
                    "comment": {"body": ni_comment},
                }
            else:
                raise Exception(
                    "The bug should either has a regressor or a needinfo target"
                )

    def get_autofix_change(self) -> dict:
        return self.autofix_regressed_by

    def get_bz_params(self, date):
        return {
            "include_fields": ["assigned_to"],
            "f1": "regressed_by",
            "o1": "isempty",
            "n2": 1,
            "f2": "regressed_by",
            "o2": "everchanged",
            "n3": 1,
            "f3": "longdesc",
            "o3": "casesubstring",
            "v3": "since this bug contains a bisection range, could you fill (if possible) the regressed_by field",
            # TODO: Nag in the duplicate target instead, making sure it doesn't already have regressed_by.
            "f4": "resolution",
            "o4": "notequals",
            "v4": "DUPLICATE",
            "emaillongdesc1": "1",
            "emailtype1": "exact",
            "email1": "bugmon@mozilla.com",
        }

    def comment_handler(self, bug, bug_id, bugs):
        range_found = False
        # We start from the last comment just in case bugmon has updated the range.
        for comment in bug["comments"][::-1]:
            if (
                "BugMon: Reduced build range" not in comment["text"]
                and "The bug appears to have been introduced in the following build range"
                not in comment["text"]
            ):
                continue

            range_found = True

            # Try to parse the regression range to find the regressor or at least somebody good to needinfo.
            pushlog_match = PUSHLOG_PAT.search(comment["text"])
            url = (
                pushlog_match.group(1).replace("pushloghtml", "json-pushes")
                + "&full=1&version=2"
            )
            r = requests.get(url)
            r.raise_for_status()

            changesets = [
                changeset
                for push in r.json()["pushes"].values()
                for changeset in push["changesets"]
                if any(not is_ignorable_path(path) for path in changeset["files"])
            ]

            regressor_bug_ids = set()
            for changeset in changesets:
                bug_match = BUG_PAT.search(changeset["desc"])
                if bug_match is not None:
                    regressor_bug_ids.add(bug_match.group(1))

            if len(regressor_bug_ids) == 1:
                # Only one bug in the regression range, we are sure about the regressor!
                bugs[bug_id]["regressor_bug_id"] = regressor_bug_ids.pop()
                break

            if "needinfo_targets" not in bugs[bug_id]:
                authors = set(changeset["author"] for changeset in changesets)
                if authors and len(authors) <= self.max_ni:
                    needinfo_targets = []
                    for author in authors:
                        author_parts = author.split("<")
                        author_email = author_parts[1][:-1]
                        bzmail = self.people.get_bzmail_from_name(author_email)
                        if not bzmail:
                            logger.warning(f"No bzmail for {author} in bug {bug_id}")
                            continue
                        needinfo_targets.append(bzmail)

                    if needinfo_targets:
                        bugs[bug_id]["needinfo_targets"] = needinfo_targets
                        break

        # Exclude bugs that do not have a range found by BugMon.
        if not range_found:
            del bugs[bug_id]

    def find_regressor_or_needinfo_target(self, bugs: dict) -> dict:
        # Needinfo assignee when there is one.
        for bug in bugs.values():
            if not utils.is_no_assignee(bug["assigned_to"]):
                bug["needinfo_targets"] = [bug["assigned_to"]]

        Bugzilla(
            bugids=self.get_list_bugs(bugs),
            commenthandler=self.comment_handler,
            commentdata=bugs,
            comment_include_fields=["text"],
        ).get_data().wait()

        bzemails = list(
            {
                bzemail
                for bug in bugs.values()
                if "needinfo_targets" in bug
                for bzemail in bug["needinfo_targets"]
            }
        )
        users = UserActivity(include_fields=["nick"]).get_bz_users_with_status(
            bzemails, keep_active=True
        )

        for bug in bugs.values():
            if "needinfo_targets" in bug:
                needinfo_targets = []
                for bzemail in bug["needinfo_targets"]:
                    user = users[bzemail]
                    if user["status"] == UserStatus.ACTIVE:
                        needinfo_targets.append(
                            {
                                "mail": bzemail,
                                "nickname": user["nick"],
                            }
                        )

                if needinfo_targets:
                    bug["needinfo_targets"] = needinfo_targets
                else:
                    del bug["needinfo_targets"]

        # Exclude all bugs where we couldn't find a definite regressor bug ID or an applicable needinfo target.
        bugs = {
            bug_id: bug
            for bug_id, bug in bugs.items()
            if "regressor_bug_id" in bug or "needinfo_targets" in bug
        }

        return bugs

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(FuzzingBisectionWithoutRegressedBy, self).get_bugs(
            date=date, bug_ids=bug_ids
        )
        bugs = self.find_regressor_or_needinfo_target(bugs)
        self.set_autofix(bugs)

        return bugs


if __name__ == "__main__":
    FuzzingBisectionWithoutRegressedBy().run()
