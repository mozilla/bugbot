# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


class Severity:
    """Severity Class

    This class is to be used to compare bug severity values.
    """

    SEVERITY_LEVELS = {"S1", "S2", "S3", "S4"}
    ACCEPTED_VALUES = SEVERITY_LEVELS | {"--", "N/A"}

    def __init__(self, severity):
        """Constructor

        prams:
            severity: the severity of the bug
        """
        assert severity in self.ACCEPTED_VALUES, "Invalid severity"
        self._value = severity

    def __bool__(self) -> bool:
        return self._value not in {"--", "N/A"}

    def __eq__(self, other) -> bool:
        return self._value == other._value or (not self and not other)

    def __lt__(self, other) -> bool:
        if not self and other:
            return True

        if self and not other or self == other:
            return False

        return self._value > other._value

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"<Severity( {self._value} )>"
