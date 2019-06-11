# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.scripts.workflow.p1_no_activity import P1NoActivity
from auto_nag.scripts.workflow.p1_no_assignee import P1NoAssignee

if __name__ == "__main__":
    P1NoAssignee().run()
    P1NoActivity().run()
