from datetime import datetime

from remoteobjects import fields
import dateutil.parser


class StringBoolean(fields.Field):
    """Decodes a boolean hidden in a string."""

    def decode(self, value):
        return bool(int(value))


class Datetime(fields.Datetime):
    """Uses python-dateutil for working with datetimes."""

    def decode(self, value):
        return dateutil.parser.parse(value)

    def encode(self, value):
        if not isinstance(value, datetime):
            raise TypeError('Value to encode %r is not a datetime' % (value,))
        return value.replace(microsecond=0).strftime(self.dateformat)
