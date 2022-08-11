# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

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


if __name__ == "__main__":
    MultiFixRegressed().run()
