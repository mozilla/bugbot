# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from bugbot.bzcleaner import BzCleaner
from bugbot.multi_autofixers import (
    MissingMergeFunctionError,
    MultiAutoFixers,
    UnexpectedToolsError,
)


class ToolOneMockup(BzCleaner):
    def __init__(self):
        self.autofix_changes = {
            "1": {
                "comment": {
                    "body": "comment body for bug 1",
                },
                "keywords": {"add": ["keyword1"]},
            },
            "2": {
                "comment": {
                    "body": "comment body for bug 2",
                }
            },
        }


class ToolTwoMockup(BzCleaner):
    def __init__(self):
        self.autofix_changes = {
            "1": {
                "comment": {
                    "body": "second tool comment body for bug 1",
                },
                "whiteboard": "TAG1",
            },
            "2": {
                "whiteboard": "TAG2",
            },
            "3": {
                "whiteboard": "TAG3",
            },
        }


class ToolThreeMockup(BzCleaner):
    def __init__(self):
        self.autofix_changes = {
            "1": {
                "type": "defect",
            },
            "2": {
                "type": "defect",
            },
        }


class ToolFourMockup(BzCleaner):
    def __init__(self):
        self.autofix_changes = {
            "1": {
                "type": "enhancement",
                "comment": {
                    "body": "unsupported comment body for bug 1",
                },
            },
        }


class MultiAutoFixersMockup(MultiAutoFixers):
    def __init__(self):
        super().__init__(
            ToolOneMockup(),
            ToolTwoMockup(),
            ToolThreeMockup(),
            comment=self.merge_comment,
        )

    @staticmethod
    def merge_comment(tools):
        if tools.keys() == {ToolOneMockup, ToolTwoMockup}:
            return {
                "body": "\n\n".join(
                    [
                        tools[ToolOneMockup]["comment"]["body"],
                        tools[ToolTwoMockup]["comment"]["body"],
                    ]
                )
            }

        raise UnexpectedToolsError(list(tools))


class MissingMergeFunctionMockup(MultiAutoFixers):
    def __init__(self):
        super().__init__(ToolThreeMockup(), ToolFourMockup())


class UnsupportedToolInMergeFunctionMockup(MultiAutoFixers):
    def __init__(self):
        super().__init__(
            ToolOneMockup(),
            ToolTwoMockup(),
            ToolThreeMockup(),
            ToolFourMockup(),
            comment=MultiAutoFixersMockup.merge_comment,
        )


class TestMultiAutoFixers(unittest.TestCase):
    def test_merge_changes(self):
        multi_autofixers = MultiAutoFixersMockup()
        changes = multi_autofixers._merge_changes_from_tools()

        self.assertEqual(changes.keys(), {"1", "2", "3"})
        self.assertEqual(
            changes["1"].keys(), {"comment", "keywords", "whiteboard", "type"}
        )
        self.assertEqual(
            changes["1"]["comment"]["body"],
            "comment body for bug 1\n\nsecond tool comment body for bug 1",
        )
        self.assertEqual(changes["1"]["whiteboard"], "TAG1")
        self.assertEqual(changes["2"].keys(), {"comment", "whiteboard", "type"})
        self.assertEqual(changes["3"].keys(), {"whiteboard"})

    def test_missed_merge_function(self):
        with self.assertRaises(MissingMergeFunctionError):
            multi_autofixers = MissingMergeFunctionMockup()
            multi_autofixers._merge_changes_from_tools()

    def test_unsported_tool_in_merge_function(self):
        with self.assertRaises(UnexpectedToolsError):
            multi_autofixers = UnsupportedToolInMergeFunctionMockup()
            multi_autofixers._merge_changes_from_tools()
