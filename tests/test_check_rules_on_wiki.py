# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import html
import re
import unittest
from unittest.mock import MagicMock, mock_open, patch

from scripts.check_rules_on_wiki import CheckWikiPage


class TestCheckWikiPage(unittest.TestCase):
    def test_html_entity_decoding(self):
        """Test that HTML entities in wiki page are properly decoded."""
        check_wiki_page = CheckWikiPage()
        github_tree_address = check_wiki_page.github_tree_address

        # Simulate wiki content with HTML entities (&#x2F; for /)
        simulated_wiki_content = f"""
        <html>
        <body>
        <a href="https:&#x2F;&#x2F;github.com&#x2F;mozilla&#x2F;bugbot&#x2F;blob&#x2F;master&#x2F;bugbot&#x2F;rules&#x2F;test1.py">test1.py</a>
        <a href="https:&#x2F;&#x2F;github.com&#x2F;mozilla&#x2F;bugbot&#x2F;blob&#x2F;master&#x2F;bugbot&#x2F;rules&#x2F;test2.py">test2.py</a>
        <a href='{github_tree_address}test3.py'>test3.py</a>
        </body>
        </html>
        """

        # Test the pattern after decoding
        decoded_content = html.unescape(simulated_wiki_content)
        pat = re.compile(rf"""['"]{re.escape(github_tree_address)}(.*)['"]""")
        rules = pat.findall(decoded_content)

        # Should find all 3 rules
        self.assertEqual(len(rules), 3)
        self.assertIn("test1.py", rules)
        self.assertIn("test2.py", rules)
        self.assertIn("test3.py", rules)

    def test_normal_urls_still_work(self):
        """Test that normal URLs without HTML entities still work."""
        check_wiki_page = CheckWikiPage()
        github_tree_address = check_wiki_page.github_tree_address

        # Simulate wiki content with normal URLs
        simulated_wiki_content = f"""
        <html>
        <body>
        <a href="{github_tree_address}rule1.py">rule1.py</a>
        <a href='{github_tree_address}rule2.py'>rule2.py</a>
        </body>
        </html>
        """

        # Test the pattern after decoding (should work the same)
        decoded_content = html.unescape(simulated_wiki_content)
        pat = re.compile(rf"""['"]{re.escape(github_tree_address)}(.*)['"]""")
        rules = pat.findall(decoded_content)

        # Should find both rules
        self.assertEqual(len(rules), 2)
        self.assertIn("rule1.py", rules)
        self.assertIn("rule2.py", rules)

    @patch("scripts.check_rules_on_wiki.urlopen")
    def test_get_rules_on_wiki_page_with_html_entities(self, mock_urlopen):
        """Test that get_rules_on_wiki_page properly handles HTML entities."""
        check_wiki_page = CheckWikiPage()
        github_tree_address = check_wiki_page.github_tree_address

        # Simulate wiki response with HTML entities
        simulated_wiki_content = f"""
        <html>
        <body>
        <a href="https:&#x2F;&#x2F;github.com&#x2F;mozilla&#x2F;bugbot&#x2F;blob&#x2F;master&#x2F;bugbot&#x2F;rules&#x2F;test_rule.py">test_rule.py</a>
        </body>
        </html>
        """

        # Mock the urlopen response
        mock_response = MagicMock()
        mock_response.read.return_value = simulated_wiki_content.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response

        # Call the method
        rules = check_wiki_page.get_rules_on_wiki_page()

        # Should find the rule
        self.assertEqual(len(rules), 1)
        self.assertIn("test_rule.py", rules)


if __name__ == "__main__":
    unittest.main()
