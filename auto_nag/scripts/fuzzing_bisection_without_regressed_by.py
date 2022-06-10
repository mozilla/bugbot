# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re

import requests
from libmozdata.bugzilla import Bugzilla, BugzillaUser

from auto_nag import logger, utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.people import People

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
    def __init__(self) -> None:
        super().__init__()
        self.autofix_regressed_by = {}
        self.bzmail_to_nickname = {}

    def description(self):
        return "Bugs with a fuzzing bisection and without regressed_by"

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = {
            "assigned_to_email": bug["assigned_to"],
            "assigned_to_nickname": bug["assigned_to_detail"]["nick"],
        }
        self.bzmail_to_nickname[bug["assigned_to"]] = bug["assigned_to_detail"]["nick"]
        return bug

    def set_autofix(self, bugs):
        for bugid, info in bugs.items():
            if "regressor_bug_id" in info:
                self.autofix_regressed_by[bugid] = {
                    "comment": {
                        "body": "Setting regressed_by field after analyzing regression range found by bugmon."
                    },
                    "regressed_by": info["regressor_bug_id"],
                }
            elif "needinfo_target" in info:
                self.add_auto_ni(
                    bugid,
                    info["needinfo_target"],
                )

    def get_autofix_change(self) -> dict[int, dict]:
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
            "emaillongdesc1": "1",
            "emailtype1": "exact",
            "email1": "bugmon@mozilla.com",
        }

    def find_regressor_or_needinfo_target(
        self, bugs: dict[str, dict]
    ) -> dict[str, dict]:
        # Needinfo assignee when there is one.
        for bug in bugs.values():
            if not utils.is_no_assignee(bug["assigned_to_email"]):
                bug["needinfo_target"] = {
                    "mail": bug["assigned_to_email"],
                    "nickname": bug["assigned_to_nickname"],
                }

        people = People.get_instance()

        # Exclude bugs that do not have a range found by BugMon.
        def comment_handler(bug, bug_id):
            range_found = False
            # We start from the last comment just in case bugmon has updated the range.
            for comment in bug["comments"][::-1]:
                if (
                    "BugMon: Reduced build range" in comment["text"]
                    or "The bug appears to have been introduced in the following build range"
                    in comment["text"]
                ):
                    range_found = True

                    # Try to parse the regression range to find the regressor or at least somebody good to needinfo.
                    pushlog_match = PUSHLOG_PAT.search(comment["text"])
                    url = (
                        pushlog_match.group(1).replace("pushloghtml", "json-pushes")
                        + "&full=1&version=2"
                    )
                    r = requests.get(url)

                    changesets = [
                        changeset
                        for push in r.json()["pushes"].values()
                        for changeset in push["changesets"]
                        if not all(
                            is_ignorable_path(path) for path in changeset["files"]
                        )
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

                    if "needinfo_target" not in bugs[bug_id]:
                        authors = set(changeset["author"] for changeset in changesets)
                        # TODO: also needinfo when there is more than one author, e.g. if there are up to three (where three should be a configurable number).
                        if len(authors) == 1:
                            author = authors.pop()
                            author_parts = author.split("<")
                            author_email = author_parts[1][:-1]
                            bzmail = people.get_bzmail_from_name(author_email)
                            if bzmail is None:
                                logger.warning(
                                    f"No bzmail for {author} for bug {bug_id}"
                                )
                                continue
                            self.bzmail_to_nickname[bzmail] = ""
                            bugs[bug_id]["needinfo_target"] = {
                                "mail": bzmail,
                                "nickname": "",
                            }
                            break

            if not range_found:
                del bugs[bug_id]

        Bugzilla(
            bugids=self.get_list_bugs(bugs),
            commenthandler=comment_handler,
            comment_include_fields=["text"],
        ).get_data().wait()

        def user_handler(user: dict) -> None:
            self.bzmail_to_nickname[user["name"]] = user["nick"]

        users = set(
            bzmail
            for bzmail, nickname in self.bzmail_to_nickname.items()
            if not nickname
        )
        if len(users) > 0:
            BugzillaUser(
                user_names=list(users),
                user_handler=user_handler,
                include_fields=["name", "nick"],
            ).wait()

        for bug in bugs.values():
            if "needinfo_target" in bug and not bug["needinfo_target"]["nickname"]:
                bug["needinfo_target"]["nickname"] = self.bzmail_to_nickname[
                    bug["needinfo_target"]["mail"]
                ]

        # Exclude all bugs where we couldn't find a definite regressor bug ID or an applicable needinfo target.
        bugs = {
            bug_id: bug
            for bug_id, bug in bugs.items()
            if "regressor_bug_id" in bug or "needinfo_target" in bug
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
