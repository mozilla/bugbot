# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import unittest

import dateutil.parser

import auto_nag.db as db


class TestDB(unittest.TestCase):
    def by_tool(self, data):
        res = {}
        for x in data:
            tool = x["tool"]
            if tool not in res:
                res[tool] = []
            res[tool].append(x)

        for tool, info in res.items():
            res[tool] = sorted(info, key=lambda x: dateutil.parser.parse(x["date"]))

        return res

    def test_bugchange(self):
        db.session.query(db.BugChange).delete()
        db.session.commit()

        with open("./auto_nag/tests/data/db_history.json", "r") as In:
            HISTORY = json.load(In)["history"]

        db.BugChange.import_from_dict(HISTORY)

        data = db.BugChange.get()
        data = list(data)

        assert len(data) == len(HISTORY)

        data = self.by_tool(HISTORY)
        for tool, info in data.items():
            _data = db.BugChange.get(name=tool).order_by(db.BugChange.date.asc())
            _data = list(_data)
            assert len(_data) == len(info)

            for expected, got in zip(info, _data):
                assert expected["tool"] == got.tool.name
                assert expected["bugid"] == got.bugid
                assert expected["date"] == str(got.get_date())

                got_extra = got.extra.extra if got.extra else ""
                assert expected["extra"] == got_extra

        db.BugChange.add("A", 123, ts=123456789, extra="")
        db.BugChange.add("A", 456, ts=123456789, extra="B")

        data = db.BugChange.get(name="A").order_by(db.BugChange.bugid.asc())
        data = list(data)

        exp = [
            {"tool": "A", "bugid": 123, "date": 123456789, "extra": ""},
            {"tool": "A", "bugid": 456, "date": 123456789, "extra": "B"},
        ]

        for expected, got in zip(exp, data):
            assert expected["tool"] == got.tool.name
            assert expected["bugid"] == got.bugid
            assert expected["date"] == got.date

            got_extra = got.extra.extra if got.extra else ""
            assert expected["extra"] == got_extra

    def test_email(self):
        db.session.query(db.Email).delete()
        db.session.commit()

        with open("./auto_nag/tests/data/db_history.json", "r") as In:
            EMAILS = json.load(In)["emails"]

        db.Email.import_from_dict(EMAILS)

        data = db.Email.get().order_by(db.Email.date.asc())
        data = list(data)

        assert len(data) == len(EMAILS)

        for expected, got in zip(EMAILS, data):
            assert expected["tool"] == got.tool.name
            assert expected["user"] == got.user.email
            assert expected["date"] == str(got.get_date())

            got_res = "Success" if got.result != 0 else "Failure"
            assert expected["result"] == got_res

            got_extra = got.extra.extra if got.extra else ""
            assert expected["extra"] == got_extra

        db.Email.add("I", ["J", "K"], "L", "Success", ts=123456789)

        data = db.Email.get(name="I")
        data = list(data)

        assert len(data) == 2
        if data[0].user.email == "K":
            data = [data[1], data[0]]

        exp = [
            {
                "tool": "I",
                "user": "J",
                "date": 123456789,
                "extra": "L",
                "result": "Success",
            },
            {
                "tool": "I",
                "user": "K",
                "date": 123456789,
                "extra": "L",
                "result": "Success",
            },
        ]

        for expected, got in zip(exp, data):
            assert expected["tool"] == got.tool.name
            assert expected["user"] == got.user.email
            assert expected["date"] == got.date

            got_res = "Success" if got.result != 0 else "Failure"
            assert expected["result"] == got_res

            got_extra = got.extra.extra if got.extra else ""
            assert expected["extra"] == got_extra
