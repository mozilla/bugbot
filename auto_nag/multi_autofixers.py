# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from collections import ChainMap, defaultdict
from typing import Any, Callable, Counter, Dict, List, Type

from auto_nag import logger, utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.nag_me import Nag

ToolsChanges = Dict[Type[BzCleaner], Any]


class UnexpectedToolsError(Exception):
    """Unexpected tools appear in merge function"""

    def __init__(self, tools: List[Type[BzCleaner]]) -> None:
        """Constructor

        Args:
            tools: the tools that change the same field.
        """
        super().__init__()
        self.tools = tools

    def __str__(self):
        return (
            "Error: merge function does not support merge fields "
            f"from '{utils.english_list(self.tools)}'"
        )


class MissingMergeFunctionError(Exception):
    """Merge function is missing"""

    def __init__(self, field: str) -> None:
        """Constructor

        Args:
            field: the field that is missing a merge function.
        """
        super().__init__()
        self.field = field

    def __str__(self):
        return f"Error: missing merge function for '{self.field}'"


class MultiAutoFixers:
    "Merge changes from multiple tools and apply them to Bugzilla at once"

    def __init__(
        self, *tools: BzCleaner, **merge_functions: Callable[[ToolsChanges], dict]
    ):
        """Constructor

        Args:
            *tools: tools to merge their changes.
            **merge_functions: functions to merge field values when multiple
                tools are changing the same field. The key should be the field
                name.
        """
        super().__init__()
        for tool in tools:
            if isinstance(tool, Nag):
                logger.warning(
                    "%s implements Nag, however, nag emails will not be merged",
                    type(tool),
                )
        self.tools = tools
        self.merge_functions = merge_functions
        self.is_dryrun: bool = True

    def description(self):
        """Return a description of the tool"""
        return "Grouped changes for the following tools: " + self.name()

    def name(self):
        """Return the name of the tool"""
        return utils.english_list([tool.name() for tool in self.tools])

    def get_args_parser(self):
        """Get the arguments from the command line"""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--production",
            dest="dryrun",
            action="store_false",
            help=(
                "If the flag is not passed, just do the query, and print the "
                "proposed changes and emails to console without emailing anyone"
            ),
        )

        return parser

    def run(self):
        """Run the tool"""
        args = self.get_args_parser().parse_args()
        self.is_dryrun = args.dryrun

        for tool in self.tools:
            tool.apply_autofix = False
            tool.run()

        new_changes = self._merge_changes_from_tools()
        no_bugmail = all(tool.no_bugmail for tool in self.tools)

        BzCleaner.apply_changes_on_bugzilla(
            self.name(), new_changes, no_bugmail, self.is_dryrun, db_extra={}
        )

    def _merge_changes_from_tools(self) -> Dict[str, dict]:
        all_changes: Dict[str, dict] = defaultdict(dict)
        for tool in self.tools:
            for bugid, changes in tool.autofix_changes.items():
                all_changes[bugid][tool.__class__] = changes

        for bugid, tools in all_changes.items():
            merged_changes = {}

            common_fields = (
                field
                for field, count in Counter(
                    field for changes in tools.values() for field in changes.keys()
                ).items()
                if count > 1
            )

            for field in common_fields:
                if field not in self.merge_functions:
                    raise MissingMergeFunctionError(field)

                tools_with_common_field = {
                    tool: changes for tool, changes in tools.items() if field in changes
                }
                merged_changes[field] = self.merge_functions[field](
                    tools_with_common_field
                )

            all_changes[bugid] = dict(ChainMap(merged_changes, *tools.values()))

        return all_changes
