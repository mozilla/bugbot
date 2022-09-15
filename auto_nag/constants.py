# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


HIGH_PRIORITY = {"P1", "P2"}
LOW_PRIORITY = {"P3", "P4", "P5"}

HIGH_SEVERITY = {"S1", "critical", "S2", "major"}
LOW_SEVERITY = {"S3", "normal", "S4", "minor", "trivial", "enhancement"}
OLD_SEVERITY_MAP = {
    "critical": "S1",
    "major": "S2",
    "normal": "S3",
    "minor": "S4",
    "trivial": "S4",
    "enhancement": "S4",
}
