# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import re
from os import path

import requests


class CheckWikiPage:
    tools_path = "auto_nag/scripts/"

    def get_tools_on_wiki_page(self):
        """Get the list of tools on the wiki page."""
        url = "https://wiki.mozilla.org/Release_Management/autonag"
        tools_address = (
            "https://github.com/mozilla/relman-auto-nag/blob/master/auto_nag/scripts/"
        )
        pat = re.compile(rf"""['"]{re.escape(tools_address)}(.*)['"]""")
        page = requests.get(url).text
        tools = pat.findall(page)

        return set(tools)

    def get_tools_in_the_tree(self):
        """Get the list of tools in the tree."""

        tools = {
            os.path.join(root, file)[len(self.tools_path) :].strip()
            for root, dirs, files in os.walk(self.tools_path)
            for file in files
            if file.endswith(".py") and file != "__init__.py"
        }

        return tools

    def check(self):
        """Check if the tools on the wiki page are up-to-date."""
        tools_in_the_tree = self.get_tools_in_the_tree()
        tools_on_wiki_page = self.get_tools_on_wiki_page()

        missed_wiki = sorted(tools_in_the_tree - tools_on_wiki_page)
        missed_tree = sorted(
            tool
            for tool in tools_on_wiki_page
            if tool not in tools_in_the_tree
            and not (
                tool.startswith("..") and path.exists(path.join(self.tools_path, tool))
            )
        )

        return missed_wiki, missed_tree

    def check_with_markdown_output(self):
        """Check if the tools on the wiki page are up-to-date and return a markdown output."""
        missed_wiki, missed_tree = self.check()
        if missed_wiki:
            print("## The following tools are not on the wiki page:")
            for tool in missed_wiki:
                print(
                    f"- [{tool}](https://github.com/mozilla/relman-auto-nag/blob/master/auto_nag/scripts/{tool})"
                )

        if missed_tree:
            print("## The following tools are not in the tree:")
            for tool in missed_tree:
                wiki_id = tool.replace("/", ".2F")
                print(
                    f"- [{tool}](https://wiki.mozilla.org/Release_Management/autonag#{wiki_id})"
                )


if __name__ == "__main__":
    CheckWikiPage().check_with_markdown_output()
