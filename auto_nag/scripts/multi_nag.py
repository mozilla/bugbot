# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.multinaggers import MultiNaggers

from .tracked_needinfo import TrackedNeedinfo
from .tracking import Tracking
from .unlanded import Unlanded


class TrackingMultiNag(MultiNaggers):
    def __init__(self):
        super(TrackingMultiNag, self).__init__(
            Unlanded("beta"),
            Unlanded("esr"),
            Tracking("beta", False),
            Tracking("beta", True),
            Tracking("central", False),
            Tracking("central", True),
            Tracking("esr", False),
            TrackedNeedinfo("beta"),
            TrackedNeedinfo("central"),
            TrackedNeedinfo("esr"),
        )

    def description(self):
        return "Get bugs which require a special attention to help release management"

    def title(self):
        return "{} -- Daily Release Tracking Alert".format(
            self.date.strftime("%A %b %d")
        )


if __name__ == "__main__":
    TrackingMultiNag().run()
