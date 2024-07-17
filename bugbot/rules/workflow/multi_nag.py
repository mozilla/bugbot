# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.erroneous_bzmail import check_erroneous_bzmail
from bugbot.multinaggers import MultiNaggers

from .no_severity_nag import NoSeverityNag
from .no_severity_ni import NoSeverityNeedInfo
from .p1_no_assignee import P1NoAssignee

# from .p1_no_activity import P1NoActivity
# from .p2_no_activity import P2NoActivity
# from .p2_merge_day import P2MergeDay


class WorkflowMultiNag(MultiNaggers):
    def __init__(self):
        super(WorkflowMultiNag, self).__init__(
            NoSeverityNeedInfo(),
            NoSeverityNag(),
            # P1NoActivity(),
            P1NoAssignee(),
            # P2NoActivity(),
        )

    def description(self):
        return "Bugs requiring special attention to help release management"

    def title(self):
        return "{} -- Severity and Priority Flags Alert".format(
            self.date.strftime("%A %b %d")
        )


if __name__ == "__main__":
    # P2MergeDay().run()
    wmn = WorkflowMultiNag()
    wmn.run()
    check_erroneous_bzmail(dryrun=wmn.is_dryrun)
