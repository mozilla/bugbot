# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict

from bugbot.multi_autofixers import MultiAutoFixers, RulesChanges, UnexpectedRulesError
from bugbot.rules.needinfo_regression_author import NeedinfoRegressionAuthor
from bugbot.rules.regression_but_type_enhancement_task import (
    RegressionButEnhancementTask,
)
from bugbot.rules.regression_set_status_flags import RegressionSetStatusFlags


class MultiFixRegressed(MultiAutoFixers):
    """Merge changes from regression related rules and apply them to Bugzilla at once"""

    def __init__(self):
        super().__init__(
            RegressionButEnhancementTask(),
            RegressionSetStatusFlags(),
            NeedinfoRegressionAuthor(),
            comment=self.__merge_comment,
            keywords=self.__merge_keywords,
        )

    @staticmethod
    def __merge_comment(rules: RulesChanges) -> dict:
        rules_to_merge = rules.keys() - {
            RegressionButEnhancementTask,  # we can ignore the comment from this rule
        }

        if len(rules_to_merge) == 1:
            return rules[next(iter(rules_to_merge))]["comment"]

        if rules_to_merge == {
            RegressionSetStatusFlags,
            NeedinfoRegressionAuthor,
        }:
            return {
                "body": "\n\n".join(
                    [
                        rules[RegressionSetStatusFlags]["comment"]["body"],
                        rules[NeedinfoRegressionAuthor]["comment"]["body"],
                    ]
                ),
                "is_private": (
                    rules[RegressionSetStatusFlags]["comment"]["is_private"]
                    or rules[NeedinfoRegressionAuthor]["comment"]["is_private"]
                ),
            }

        raise UnexpectedRulesError(rules_to_merge)

    @staticmethod
    def __merge_keywords(rules: RulesChanges) -> dict:
        merged_changes = defaultdict(set)
        for changes in rules.values():
            if "keywords" not in changes:
                continue

            for action, value in changes["keywords"].items():
                if isinstance(value, str):
                    value = [value]

                merged_changes[action].update(value)

        return {action: list(values) for action, values in merged_changes.items()}


if __name__ == "__main__":
    MultiFixRegressed().run()
