# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from collections import ChainMap, defaultdict
from typing import Any, Callable, Counter, Dict, Iterable, Type

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.nag_me import Nag

RulesChanges = Dict[Type[BzCleaner], Any]


class UnexpectedRulesError(Exception):
    """Unexpected rules appear in merge function"""

    def __init__(self, rules: Iterable[Type[BzCleaner]]) -> None:
        """Constructor

        Args:
            rules: the rules that change the same field.
        """
        super().__init__()
        self.rules = rules

    def __str__(self):
        return (
            "Error: merge function does not support merge fields "
            f"from '{utils.english_list([rule.__name__ for rule in self.rules])}'"
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
    "Merge changes from multiple rules and apply them to Bugzilla at once"

    def __init__(
        self, *rules: BzCleaner, **merge_functions: Callable[[RulesChanges], dict]
    ):
        """Constructor

        Args:
            *rules: rules to merge their changes.
            **merge_functions: functions to merge field values when multiple
                rules are changing the same field. The key should be the field
                name.
        """
        super().__init__()
        for rule in rules:
            if isinstance(rule, Nag):
                logger.warning(
                    "%s implements Nag, however, nag emails will not be merged",
                    type(rule),
                )
        self.rules = rules
        self.merge_functions = merge_functions
        self.is_dryrun: bool = True

    def description(self):
        """Return a description of the rule"""
        return "Grouped changes for the following rules: " + self.name()

    def name(self):
        """Return the name of the rule"""
        return utils.english_list([rule.name() for rule in self.rules])

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
        """Run the rule"""
        args = self.get_args_parser().parse_args()
        self.is_dryrun = args.dryrun

        for rule in self.rules:
            rule.apply_autofix = False
            rule.run()

        new_changes = self._merge_changes_from_rules()
        no_bugmail = all(rule.no_bugmail for rule in self.rules)

        BzCleaner.apply_changes_on_bugzilla(
            self.name(), new_changes, no_bugmail, self.is_dryrun, db_extra={}
        )

    def _merge_changes_from_rules(self) -> Dict[str, dict]:
        all_changes: Dict[str, dict] = defaultdict(dict)
        for rule in self.rules:
            for bugid, changes in rule.autofix_changes.items():
                all_changes[bugid][rule.__class__] = changes

        for bugid, rules in all_changes.items():
            merged_changes = {}

            common_fields = (
                field
                for field, count in Counter(
                    field for changes in rules.values() for field in changes.keys()
                ).items()
                if count > 1
            )

            for field in common_fields:
                if field not in self.merge_functions:
                    raise MissingMergeFunctionError(field)

                rules_with_common_field = {
                    rule: changes for rule, changes in rules.items() if field in changes
                }
                merged_changes[field] = self.merge_functions[field](
                    rules_with_common_field
                )

            all_changes[bugid] = dict(ChainMap(merged_changes, *rules.values()))

        return all_changes
