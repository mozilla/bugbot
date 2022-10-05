# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict

from auto_nag.multi_autofixers import (
    MultiAutoFixers,
    ToolsChanges,
    UnexpectedToolsError,
)
from auto_nag.scripts.needinfo_regression_author import NeedinfoRegressionAuthor
from auto_nag.scripts.regression_but_type_enhancement_task import (
    RegressionButEnhancementTask,
)
from auto_nag.scripts.regression_set_status_flags import RegressionSetStatusFlags


class MultiFixRegressed(MultiAutoFixers):
    """Merge changes from regression related tools and apply them to Bugzilla at once"""

    def __init__(self):
        super().__init__(
            RegressionButEnhancementTask(),
            RegressionSetStatusFlags(),
            NeedinfoRegressionAuthor(),
            comment=self.__merge_comment,
            keywords=self.__merge_keywords,
        )

    @staticmethod
    def __merge_comment(tools: ToolsChanges) -> dict:
        if tools.keys() == {RegressionSetStatusFlags, NeedinfoRegressionAuthor}:
            return {
                "body": "\n\n".join(
                    [
                        tools[RegressionSetStatusFlags]["comment"]["body"],
                        tools[NeedinfoRegressionAuthor]["comment"]["body"],
                    ]
                ),
            }

        raise UnexpectedToolsError(list(tools))

    @staticmethod
    def __merge_keywords(tools: ToolsChanges) -> dict:
        merged_changes = defaultdict(set)
        for changes in tools.values():
            if "keywords" in changes:
                for action, value in changes["keywords"].items():
                    if isinstance(value, str):
                        value = [value]

                    merged_changes[action].update(value)

        return {
            "keywords": {
                action: list(values) for action, values in merged_changes.items()
            }
        }


if __name__ == "__main__":
    MultiFixRegressed().run()
