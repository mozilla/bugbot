# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import logging
import os
import re
from os import path
from typing import Optional
from urllib.request import Request, urlopen


class CheckWikiPage:
    """Check if the rules on the wiki page are up-to-date."""

    wiki_page_url = "https://wiki.mozilla.org/BugBot"
    github_tree_address = "https://github.com/mozilla/bugbot/blob/master/bugbot/rules/"
    rules_path = "bugbot/rules/"

    deleted_rules = {
        "fuzzing_bisection_without_regressed_by.py",  # replaced with `bisection_without_regressed_by.py`
        "severity_tracked.py",  # dropped in favor of `tracked_attention.py`
        "tracked_bad_severity.py",  # dropped in favor of `tracked_attention.py`
        "newbie_with_ni.py",
    }

    skipped_rules = {
        # Disabled rules:
        "workflow/p1.py",
        "workflow/p2.py",
        "workflow/p2_no_activity.py",
        "workflow/p3_p4_p5.py",
        # Temporary scripts:
        "survey_sec_bugs.py",  # not running by cron
        # Not user-facing rules:
        "stepstoreproduce.py",  # the autofix is currently disabled
        "triage_owner_rotations.py",
        "triage_rotations_outdated.py",
        "vacant_team_manager.py",
        "defect_with_please_or_enable.py",
        "missed_landing_comment.py",
        "meta_defect.py",
        "feature_but_type_defect.py",
        "workflow/multi_nag.py",
        "multi_nag.py",
        "multifix_regression.py",
        "several_dups.py",
        "several_votes.py",
        "several_cc.py",
        "several_comments.py",
        "several_see_also.py",
        "pdfjs_update.py",
        "leave_open_sec.py",
        "webcompat_score.py",
        # Experimental rules:
        "accessibilitybug.py",
        "performancebug.py",
    }

    def __init__(self) -> None:
        self.missed_tree: Optional[list] = None
        self.missed_wiki: Optional[list] = None

    def get_rules_on_wiki_page(self) -> set:
        """Get the list of rules on the wiki page."""
        req = Request(self.wiki_page_url)

        # When running on GitHub Actions, we need to add the token to the request
        # to access the wiki page. Otherwise, we get a 403 error.
        wiki_token = os.environ.get("WIKI_TOKEN_GHA")
        if wiki_token:
            req.add_header("bugbotgha", wiki_token)

        with urlopen(req) as resp:
            wiki_page_content = resp.read().decode("utf-8")

        pat = re.compile(rf"""['"]{re.escape(self.github_tree_address)}(.*)['"]""")
        rules = pat.findall(wiki_page_content)

        if not rules:
            logging.error("The content of the wiki page is:\n%s", wiki_page_content)
            raise Exception(f"No rules found on the wiki page {self.wiki_page_url}")

        return set(rules)

    def get_rules_in_the_tree(self) -> set:
        """Get the list of rules in the tree."""

        rules = {
            os.path.join(root, file)[len(self.rules_path) :].strip()
            for root, dirs, files in os.walk(self.rules_path)
            for file in files
            if file.endswith(".py") and file != "__init__.py"
        }

        if not rules:
            raise Exception(f"No rules found in the tree {self.rules_path}")

        return rules

    def check(self) -> None:
        """Check if the rules on the wiki page are up-to-date."""
        rules_in_the_tree = self.get_rules_in_the_tree()
        rules_on_wiki_page = self.get_rules_on_wiki_page()

        self.missed_wiki = sorted(
            rule
            for rule in rules_in_the_tree
            if rule not in rules_on_wiki_page and rule not in self.skipped_rules
        )
        self.missed_tree = sorted(
            rule
            for rule in rules_on_wiki_page
            if rule not in rules_in_the_tree
            and rule not in self.deleted_rules
            and not (
                rule.startswith("..") and path.exists(path.join(self.rules_path, rule))
            )
        )

    def print_markdown_output(self) -> None:
        """Print the output in markdown format."""

        if self.missed_wiki is None or self.missed_tree is None:
            self.check()

        if self.missed_wiki:
            print("## The following rules are not on the wiki page:")
            for rule in self.missed_wiki:
                print(f"- [{rule}]({self.github_tree_address + rule})")

        if self.missed_tree:
            print("## The following rules are not in the tree:")
            for rule in self.missed_tree:
                wiki_id = rule.replace("/", ".2F")
                print(f"- [{rule}]({self.wiki_page_url}#{wiki_id})")

    def raise_on_mismatch(self) -> None:
        """Raise an exception if the rules on the wiki page are not up-to-date."""
        if self.missed_wiki is None or self.missed_tree is None:
            self.check()

        if self.missed_wiki or self.missed_tree:
            raise Exception(
                "The rules in the tree and on the wiki page are not in sync."
            )

    def check_with_markdown_output(self):
        """Check if the rules on the wiki page are up-to-date and return a markdown output."""
        if self.missed_wiki is None or self.missed_tree is None:
            self.check()

        if self.missed_wiki:
            print("## The following rules are not on the wiki page:")
            for rule in self.missed_wiki:
                print(f"- [{rule}]({self.github_tree_address + rule})")

        if self.missed_tree:
            print("## The following rules are not in the tree:")
            for rule in self.missed_tree:
                wiki_id = rule.replace("/", ".2F")
                print(f"- [{rule}]({self.wiki_page_url}#{wiki_id})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check if the rules on the wiki page are up-to-date."
    )
    parser.add_argument(
        "-ci",
        "--error-on-mismatch",
        dest="error_on_mismatch",
        action="store_true",
        default=False,
        help="Throw an error if the rules are not up-to-date.",
    )
    args = parser.parse_args()

    check_wiki_page = CheckWikiPage()
    check_wiki_page.print_markdown_output()
    if args.error_on_mismatch:
        check_wiki_page.raise_on_mismatch()
