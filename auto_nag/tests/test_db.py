# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import dateutil.parser
from mock import patch
import unittest

import auto_nag.db as db
from auto_nag.history import History


class TestDB(unittest.TestCase):

    HISTORY = [
        {
            "tool": "no_assignee",
            "bugid": 1523712,
            "date": "2019-01-31 13:03:06+00:00",
            "extra": "emilio@crisal.io",
        },
        {
            "tool": "no_crashes",
            "bugid": 753667,
            "date": "2018-11-30 13:05:04+00:00",
            "extra": "",
        },
        {
            "tool": "leave_open_no_activity",
            "bugid": 1359875,
            "date": "2018-12-12 13:06:43+00:00",
            "extra": "gl@mozilla.com",
        },
        {
            "tool": "summary_meta_missing",
            "bugid": 1400842,
            "date": "2018-12-12 13:06:18+00:00",
            "extra": "",
        },
        {
            "tool": "leave_open",
            "bugid": 1474570,
            "date": "2018-11-07 13:01:21+00:00",
            "extra": "",
        },
        {
            "tool": "no_assignee",
            "bugid": 1507340,
            "date": "2018-11-15 13:02:06+00:00",
            "extra": "mh+mozilla@glandium.org",
        },
        {
            "tool": "assignee_but_unconfirmed",
            "bugid": 1540111,
            "date": "2019-03-29 13:56:06+00:00",
            "extra": "",
        },
        {
            "tool": "no_crashes",
            "bugid": 696336,
            "date": "2018-12-23 13:05:41+00:00",
            "extra": "",
        },
        {
            "tool": "assignee_but_unconfirmed",
            "bugid": 1540113,
            "date": "2019-03-29 13:56:05+00:00",
            "extra": "",
        },
        {
            "tool": "not_landed",
            "bugid": 1531926,
            "date": "2019-03-27 13:07:05+00:00",
            "extra": "rjesup@jesup.org",
        },
        {
            "tool": "no_assignee",
            "bugid": 1531927,
            "date": "2019-03-07 05:15:24+00:00",
            "extra": "egao@mozilla.com",
        },
        {
            "tool": "nighty_reopened",
            "bugid": 1531927,
            "date": "2019-03-07 19:15:46+00:00",
            "extra": "",
        },
        {
            "tool": "no_assignee",
            "bugid": 1204247,
            "date": "2018-12-14 17:01:23+00:00",
            "extra": "sharma.divyansh.501@iitg.ernet.in",
        },
        {
            "tool": "not_landed",
            "bugid": 1490968,
            "date": "2019-03-21 13:09:51+00:00",
            "extra": "qiaopengcheng-hf@loongson.cn",
        },
        {
            "tool": "summary_meta_missing",
            "bugid": 1458202,
            "date": "2018-11-08 08:10:56+00:00",
            "extra": "",
        },
        {
            "tool": "leave_open_no_activity",
            "bugid": 1450012,
            "date": "2018-11-23 13:11:57+00:00",
            "extra": "dustin@mozilla.com",
        },
        {
            "tool": "no_assignee",
            "bugid": 1515549,
            "date": "2019-01-11 13:00:58+00:00",
            "extra": "achronop@gmail.com",
        },
        {
            "tool": "leave_open_no_activity",
            "bugid": 1425440,
            "date": "2018-11-22 15:07:09+00:00",
            "extra": "amarchesini@mozilla.com",
        },
        {
            "tool": "leave_open",
            "bugid": 1425440,
            "date": "2018-11-23 13:01:25+00:00",
            "extra": "",
        },
        {
            "tool": "nighty_reopened",
            "bugid": 1523755,
            "date": "2019-02-08 13:07:03+00:00",
            "extra": "",
        },
        {
            "tool": "no_crashes",
            "bugid": 876589,
            "date": "2018-12-27 13:06:28+00:00",
            "extra": "",
        },
        {
            "tool": "no_assignee",
            "bugid": 1540142,
            "date": "2019-04-04 05:15:20+00:00",
            "extra": "petr.sumbera@oracle.com",
        },
        {
            "tool": "no_crashes",
            "bugid": 1425461,
            "date": "2019-03-15 00:15:24+00:00",
            "extra": "",
        },
        {
            "tool": "regression",
            "bugid": 1425461,
            "date": "2019-03-15 13:47:28+00:00",
            "extra": "",
        },
        {
            "tool": "no_assignee",
            "bugid": 1540151,
            "date": "2019-04-01 08:52:15+00:00",
            "extra": "dwalsh@mozilla.com",
        },
        {
            "tool": "leave_open_no_activity",
            "bugid": 1073209,
            "date": "2018-11-23 13:11:55+00:00",
            "extra": "dbolter@mozilla.com",
        },
        {
            "tool": "no_assignee",
            "bugid": 1515582,
            "date": "2019-02-12 13:02:23+00:00",
            "extra": "bzbarsky@mit.edu",
        },
    ]

    EMAILS = [
        {
            'tool': 'A',
            'user': 'B',
            'date': '2019-02-12 13:02:23+00:00',
            'extra': 'C',
            'result': 'Success',
        },
        {
            'tool': 'D',
            'user': 'E',
            'date': '2019-02-13 13:02:23+00:00',
            'extra': 'F',
            'result': 'Failure',
        },
        {
            'tool': 'G',
            'user': 'H',
            'date': '2019-02-14 13:02:23+00:00',
            'extra': '',
            'result': 'Success',
        },
    ]

    def by_tool(self, data):
        res = {}
        for x in data:
            tool = x['tool']
            if tool not in res:
                res[tool] = []
            res[tool].append(x)

        for tool, info in res.items():
            res[tool] = sorted(info, key=lambda x: dateutil.parser.parse(x['date']))

        return res

    def test_bugchange(self):
        with patch.object(History, 'get', return_value=TestDB.HISTORY):
            db.session.query(db.BugChange).delete()
            db.session.commit()

            db.init()

            data = db.BugChange.get()
            data = list(data)

            assert len(data) == len(TestDB.HISTORY)

            data = self.by_tool(TestDB.HISTORY)
            for tool, info in data.items():
                _data = db.BugChange.get(name=tool).order_by(db.BugChange.date.asc())
                _data = list(_data)
                assert len(_data) == len(info)

                for expected, got in zip(info, _data):
                    assert expected['tool'] == got.tool.name
                    assert expected['bugid'] == got.bugid
                    assert expected['date'] == str(got.get_date())

                    got_extra = got.extra.extra if got.extra else ''
                    assert expected['extra'] == got_extra

        db.BugChange.add('A', 123, ts=123456789, extra='')
        db.BugChange.add('A', 456, ts=123456789, extra='B')

        data = db.BugChange.get(name='A').order_by(db.BugChange.bugid.asc())
        data = list(data)

        exp = [
            {'tool': 'A', 'bugid': 123, 'date': 123456789, 'extra': ''},
            {'tool': 'A', 'bugid': 456, 'date': 123456789, 'extra': 'B'},
        ]

        for expected, got in zip(exp, data):
            assert expected['tool'] == got.tool.name
            assert expected['bugid'] == got.bugid
            assert expected['date'] == got.date

            got_extra = got.extra.extra if got.extra else ''
            assert expected['extra'] == got_extra

    def test_email(self):
        db.session.query(db.Email).delete()
        db.session.commit()

        db.Email.read_dict(TestDB.EMAILS)

        data = db.Email.get().order_by(db.Email.date.asc())
        data = list(data)

        assert len(data) == len(TestDB.EMAILS)

        for expected, got in zip(TestDB.EMAILS, data):
            assert expected['tool'] == got.tool.name
            assert expected['user'] == got.user.email
            assert expected['date'] == str(got.get_date())

            got_res = 'Success' if got.result != 0 else 'Failure'
            assert expected['result'] == got_res

            got_extra = got.extra.extra if got.extra else ''
            assert expected['extra'] == got_extra

        db.Email.add('I', ['J', 'K'], 'L', 'Success', ts=123456789)

        data = db.Email.get(name='I')
        data = list(data)

        assert len(data) == 2
        if data[0].user.email == 'K':
            data = [data[1], data[0]]

        exp = [
            {
                'tool': 'I',
                'user': 'J',
                'date': 123456789,
                'extra': 'L',
                'result': 'Success',
            },
            {
                'tool': 'I',
                'user': 'K',
                'date': 123456789,
                'extra': 'L',
                'result': 'Success',
            },
        ]

        for expected, got in zip(exp, data):
            assert expected['tool'] == got.tool.name
            assert expected['user'] == got.user.email
            assert expected['date'] == got.date

            got_res = 'Success' if got.result != 0 else 'Failure'
            assert expected['result'] == got_res

            got_extra = got.extra.extra if got.extra else ''
            assert expected['extra'] == got_extra
