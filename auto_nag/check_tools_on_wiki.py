# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import os
import re
from os import path
from typing import Optional

import requests


class CheckWikiPage:
    """Check if the tools on the wiki page are up-to-date."""

    wiki_page_url = "https://wiki.mozilla.org/Release_Management/autonag"
    github_tree_address = (
        "https://github.com/mozilla/relman-auto-nag/blob/master/auto_nag/scripts/"
    )
    tools_path = "auto_nag/scripts/"

    deleted_tools = {
        "fuzzing_bisection_without_regressed_by.py"  # replaced with `bisection_without_regressed_by.py`
        "severity_tracked.py"  # dropped in favor of `tracked_attention.py`
    }

    skipped_tools = {
        "multi_nag.py",
        "multifix_regression.py",
        "several_dups.py",
        "lot_of_votes.py",
        "lot_of_cc.py",
        "pdfjs_tag_change.py",
        "pdfjs_update.py",
    }

    def __init__(self) -> None:
        self.missed_tree: Optional[list] = None
        self.missed_wiki: Optional[list] = None

    def get_tools_on_wiki_page(self) -> set:
        """Get the list of tools on the wiki page."""
        resp = requests.get(self.wiki_page_url)
        resp.raise_for_status()

        pat = re.compile(rf"""['"]{re.escape(self.github_tree_address)}(.*)['"]""")
        tools = pat.findall(resp.text)

        if not tools:
            raise Exception(f"No tools found on the wiki page {self.wiki_page_url}")

        return set(tools)

    def get_tools_in_the_tree(self) -> set:
        """Get the list of tools in the tree."""

        tools = {
            os.path.join(root, file)[len(self.tools_path) :].strip()
            for root, dirs, files in os.walk(self.tools_path)
            for file in files
            if file.endswith(".py") and file != "__init__.py"
        }

        if not tools:
            raise Exception(f"No tools found in the tree {self.tools_path}")

        return tools

    def check(self) -> None:
        """Check if the tools on the wiki page are up-to-date."""
        tools_in_the_tree = self.get_tools_in_the_tree()
        tools_on_wiki_page = self.get_tools_on_wiki_page()

        self.missed_wiki = sorted(
            tool
            for tool in tools_in_the_tree
            if tool not in tools_on_wiki_page and tool not in self.skipped_tools
        )
        self.missed_tree = sorted(
            tool
            for tool in tools_on_wiki_page
            if tool not in tools_in_the_tree
            and tool not in self.deleted_tools
            and not (
                tool.startswith("..") and path.exists(path.join(self.tools_path, tool))
            )
        )

    def print_markdown_output(self) -> None:
        """Print the output in markdown format."""

        if self.missed_wiki is None or self.missed_tree is None:
            self.check()

        if self.missed_wiki:
            print("## The following tools are not on the wiki page:")
            for tool in self.missed_wiki:
                print(
                    f"- [{tool}](https://github.com/mozilla/relman-auto-nag/blob/master/auto_nag/scripts/{tool})"
                )

        if self.missed_tree:
            print("## The following tools are not in the tree:")
            for tool in self.missed_tree:
                wiki_id = tool.replace("/", ".2F")
                print(
                    f"- [{tool}](https://wiki.mozilla.org/Release_Management/autonag#{wiki_id})"
                )

    def raise_on_mismatch(self) -> None:
        """Raise an exception if the tools on the wiki page are not up-to-date."""
        if self.missed_wiki is None or self.missed_tree is None:
            self.check()

        if self.missed_wiki or self.missed_tree:
            raise Exception(
                "The tools in the tree and on the wiki page are not in sync."
            )

    def check_with_markdown_output(self):
        """Check if the tools on the wiki page are up-to-date and return a markdown output."""
        if self.missed_wiki is None or self.missed_tree is None:
            self.check()

        if self.missed_wiki:
            print("## The following tools are not on the wiki page:")
            for tool in self.missed_wiki:
                print(
                    f"- [{tool}](https://github.com/mozilla/relman-auto-nag/blob/master/auto_nag/scripts/{tool})"
                )

        if self.missed_tree:
            print("## The following tools are not in the tree:")
            for tool in self.missed_tree:
                wiki_id = tool.replace("/", ".2F")
                print(
                    f"- [{tool}](https://wiki.mozilla.org/Release_Management/autonag#{wiki_id})"
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check if the tools on the wiki page are up-to-date."
    )
    parser.add_argument(
        "-ci",
        "--error-on-mismatch",
        dest="error_on_mismatch",
        action="store_true",
        default=False,
        help="Throw an error if the tools are not up-to-date.",
    )
    args = parser.parse_args()

    check_wiki_page = CheckWikiPage()
    check_wiki_page.print_markdown_output()
    if args.error_on_mismatch:
        check_wiki_page.raise_on_mismatch()
