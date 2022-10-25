# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import re

import requests


class CheckWikiPage:
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
        tools_path = "auto_nag/scripts/"
        tools = {
            os.path.join(root, file)[len(tools_path) :].strip()
            for root, dirs, files in os.walk(tools_path)
            for file in files
            if file.endswith(".py") and file != "__init__.py"
        }

        return tools

    def check(self):
        """Check if the tools on the wiki page are up-to-date."""
        tools_in_the_tree = self.get_tools_in_the_tree()
        tools_on_wiki_page = self.get_tools_on_wiki_page()

        missed_wiki = tools_in_the_tree - tools_on_wiki_page
        missed_tree = tools_on_wiki_page - tools_in_the_tree

        return missed_wiki, missed_tree


if __name__ == "__main__":
    missed_wiki, missed_tree = CheckWikiPage().check()
    if missed_wiki:
        print("\nThe following tools are not on the wiki page:")
        for tool in missed_wiki:
            print(f"\t- {tool}")

    if missed_tree:
        print("\nThe following tools are not in the tree:")
        for tool in missed_tree:
            print(f"\t- {tool}")
