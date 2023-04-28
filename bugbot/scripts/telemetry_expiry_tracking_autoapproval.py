# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot.bzcleaner import BzCleaner


class TrackTelemetryExpiry(BzCleaner):
    def __init__(self):
        super(TrackTelemetryExpiry, self).__init__()
        # need to check that versions aren't messy
        if not self.init_versions():
            return

    def description(self):
        return "Automatically approve tracking request for expiring telemetry probe"

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        params = {
            "reporter": "telemetry-probes@mozilla.bugs",
            "f1": "cf_tracking_firefox_nightly",
            "o1": "equals",
            "v1": "?",
        }

        return params

    def get_autofix_change(self):
        tracking_nightly = f"cf_tracking_firefox{self.versions['central']}"
        return {
            tracking_nightly: "+",
        }


if __name__ == "__main__":
    TrackTelemetryExpiry().run()
