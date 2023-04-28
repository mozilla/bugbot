# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


class WebcompatPriority:
    """Webcompat priority Class

    This class is to be used to compare webcompat priority values.
    """

    PRIORITY_LEVELS = {"P1", "P2", "P3"}
    TRIAGE_REQUIRED_VALUES = {"?", "revisit"}
    EMPTY_VALUES = {"--", "-"}
    NOT_EMPTY_VALUES = PRIORITY_LEVELS | TRIAGE_REQUIRED_VALUES
    ACCEPTED_VALUES = NOT_EMPTY_VALUES | EMPTY_VALUES

    def __init__(self, priority):
        """Constructor

        prams:
            severity: the severity of the bug
        """
        assert priority in self.ACCEPTED_VALUES, "Invalid priority"
        self._value = priority

    def __bool__(self) -> bool:
        return self._value in self.PRIORITY_LEVELS

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
        return f"<WebcompatPriority( {self._value} )>"
