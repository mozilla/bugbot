# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


class Handler(object):
    def __init__(self, func=None, data=None):
        self.handler = func
        self.data = data

    def handle(self, *args):
        if self.handler:
            if self.data is not None:
                args += (self.data,)
                self.handler(*args)
            else:
                self.handler(*args)

    def _as_list(self):
        return [self]

    def isactive(self):
        return self.handler is not None

    def clone(self):
        return Handler(self.func, self.data)

    def merge(self, handler, clone=False):
        if self.isactive():
            if handler.isactive():
                return MultipleHandler(self, handler)
            else:
                return self.clone() if clone else self
        else:
            return handler.clone() if clone else handler

    @staticmethod
    def get(h, data=None):
        if isinstance(h, Handler):
            return h
        elif data is None and isinstance(h, tuple) and len(h) == 2:
            return Handler(*h)
        elif isinstance(h, list):
            return MultipleHandler(*tuple(h))
        elif isinstance(h, tuple):
            return MultipleHandler(*h)
        else:
            return Handler(h, data)


class MultipleHandler(Handler):
    def __init__(self, *args):
        self.handler = []
        for arg in args:
            self.handler.extend(Handler.get(arg)._as_list())

    def handle(self, *args):
        for h in self.handler:
            if h.isactive():
                h.handle(*args)

    def _as_list(self):
        return self.handler

    def isactive(self):
        for h in self.handler:
            if h.isactive():
                return True
        return False

    def clone(self):
        hdlers = []
        for h in self.handler:
            hdlers.append(h.clone())
        mh = MultipleHandler()
        mh.handler = hdlers

        return mh
