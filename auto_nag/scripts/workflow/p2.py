# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.scripts.workflow.p2_no_activity import P2NoActivity
from auto_nag.scripts.workflow.p2_merge_day import P2MergeDay


if __name__ == '__main__':
    P2MergeDay().run()
    P2NoActivity().run()
