# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.multinaggers import MultiNaggers
from .no_priority import NoPriority
from .p1_no_activity import P1NoActivity
from .p1_no_assignee import P1NoAssignee
from .p2_no_activity import P2NoActivity
from .p2_merge_day import P2MergeDay

class WorkflowMultiNag(MultiNaggers):
    def __init__(self):
        super(WorkflowMultiNag, self).__init__(
            NoPriority('first'),
            NoPriority('second'),
            P1NoActivity(),
            P1NoAssignee(),
            P2NoActivity(),
        )

    def description(self):
        return 'Bugs requiring special attention to help release management'

    def title(self):
        return '{} -- Daily Priority Flag Alert'.format(self.date.strftime('%A %b %d'))


if __name__ == '__main__':
    P2MergeDay().run()
    WorkflowMultiNag().run()
