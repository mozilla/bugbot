# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import calendar
import csv
import dateutil.parser
from filelock import FileLock
import json
from libmozdata import utils as lmdutils
import os
import six
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import Column, ForeignKey, Integer, String

from auto_nag import logger, utils
from auto_nag.history import History


Base = declarative_base()
lock_path = utils.get_config('common', 'lock')
db_path = utils.get_config('common', 'database')
engine = create_engine(db_path)
DBSession = sessionmaker(bind=engine)
Base.metadata.bind = engine
session = DBSession()


def clear():
    Base.metadata.drop_all()
    session.commit()


def create():
    if not engine.dialect.has_table(engine, 'tools'):
        Base.metadata.create_all(engine)
        init()


def init():
    hist = History().get()
    logger.info('Put history in db: start...')
    BugChange.read_dict(hist)
    logger.info('Put history in db: end.')


def get_ts(date, default=0):
    if isinstance(date, six.integer_types):
        return date
    if date:
        if isinstance(date, six.string_types):
            date = dateutil.parser.parse(date)
        date = int(calendar.timegm(date.timetuple()))
        return date
    if default == 'now':
        return lmdutils.get_timestamp('now')
    return default


class Tool(Base):
    __tablename__ = 'tools'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True)
    bugchanges = relationship('BugChange', backref='tool')
    sentmails = relationship('SentEmail', backref='tool')

    def __init__(self, name):
        self.name = name

    @staticmethod
    def get(name):
        e = session.query(Tool).filter(Tool.name == name).first()
        if e:
            return e

        e = Tool(name)
        session.add(e)
        session.commit()

        return e

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.__repr__()


class BugChange(Base):
    __tablename__ = 'bugchanges'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tool_id = Column(Integer, ForeignKey('tools.id', ondelete='CASCADE'))
    extra_id = Column(Integer, ForeignKey('extras.id', ondelete='CASCADE'))
    date = Column(Integer)
    bugid = Column(Integer)

    def __init__(self, tool, date, bugid, extra):
        self.tool = Tool.get(tool)
        self.date = get_ts(date)
        self.bugid = int(bugid)
        self.extra = Extra.get(extra)

    def get_date(self):
        return lmdutils.get_date_from_timestamp(self.date)

    @staticmethod
    def add(tool, bugid, ts=lmdutils.get_timestamp('now'), extra=''):
        with FileLock(lock_path):
            session.add(BugChange(tool, ts, bugid, extra))
            session.commit()

    @staticmethod
    def get(name=None, start_date=None, end_date=None):
        with FileLock(lock_path):
            start_date = get_ts(start_date, default=0)
            end_date = get_ts(start_date, default='now')
            if name:
                rs = (
                    session.query(BugChange)
                    .join(BugChange.tool)
                    .filter(
                        Tool.name == name,
                        BugChange.date >= start_date,
                        BugChange.date < end_date,
                    )
                )
            else:
                rs = session.query(BugChange).filter(
                    BugChange.date >= start_date, BugChange.date < end_date
                )

            return [r for r in rs]

    @staticmethod
    def has_already_nagged(bugids, name=None, start_date=None, end_date=None):
        with FileLock(lock_path):
            data = {int(bugid): False for bugid in bugids}
            bugids = list(data.keys())
            start_date = get_ts(start_date, default=0)
            end_date = get_ts(start_date, default='now')
            if name:
                res = (
                    session.query(BugChange.bugid)
                    .join(BugChange.tool)
                    .filter(
                        Tool.name == name,
                        BugChange.bugid.in_(bugids),
                        BugChange.date >= start_date,
                        BugChange.date < end_date,
                    )
                )
            else:
                res = session.query(BugChange.bugid).filter(
                    BugChange.bugid.in_(bugids),
                    BugChange.date >= start_date,
                    BugChange.date < end_date,
                )

            for r in res:
                data[r.bugid] = True
            return data

    @staticmethod
    def dump(path=''):
        res = session.query(BugChange).join(BugChange.tool)
        ext = os.path.splitext(path)[1]
        if ext == '.csv':
            with open(path, 'w') as Out:
                writer = csv.writer(Out, delimiter=',')
                writer.writerow(['Tool', 'Bugid', 'Date', 'Extra'])
                for x in res:
                    extra = x.extra.extra if x.extra else ''
                    writer.writerow([x.tool.name, x.bugid, str(x.get_date()), extra])
        elif ext == '.json':
            with open(path, 'w') as Out:
                data = []
                for x in res:
                    extra = x.extra.extra if x.extra else ''
                    data.append(
                        {
                            'tool': x.tool.name,
                            'bugid': x.bugid,
                            'date': str(x.get_date()),
                            'extra': extra,
                        }
                    )
                json.dump(data, Out)
        else:
            for x in res:
                print(x)

    @staticmethod
    def read_dict(data):
        for x in data:
            tool, date, bugid, extra = (
                x[f] for f in ['tool', 'date', 'bugid', 'extra']
            )
            session.add(BugChange(tool, date, bugid, extra))
        session.commit()

    @staticmethod
    def read_from(path):
        ext = os.path.splitext(path)[1]
        if ext == '.csv':
            with open(path, 'r') as In:
                reader = csv.reader(In, delimiter=',')
                for tool, bugid, date, extra in reader:
                    session.add(BugChange(tool, date, bugid, extra))
                session.commit()
        elif ext == '.json':
            with open(path, 'r') as In:
                data = json.load(In)
                BugChange.read_dict(data)
        else:
            assert False, 'Unable to read file: {}'.format(path)

    def __repr__(self):
        extra = self.extra.extra if self.extra else ''
        return '<Bug change ({}): bug {}, the {}, extra={}>'.format(
            self.tool, self.bugid, self.get_date(), extra
        )

    def __str__(self):
        return self.__repr__()


class Email(Base):
    __tablename__ = 'emails'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(254), unique=True)
    sentmails = relationship('SentEmail', backref='email')

    def __init__(self, email):
        self.email = email

    @staticmethod
    def get(email):
        e = session.query(Email).filter(Email.email == email).first()
        if e:
            return e

        e = Email(email)
        session.add(e)
        session.commit()

        return e

    @staticmethod
    def dump():
        for x in session.query(Email):
            print(x)

    def __repr__(self):
        return self.email

    def __str__(self):
        return self.__repr__()


class Extra(Base):
    __tablename__ = 'extras'

    id = Column(Integer, primary_key=True, autoincrement=True)
    extra = Column(String(256), unique=True)
    sentmails = relationship('SentEmail', backref='extra')
    bugchanges = relationship('BugChange', backref='extra')

    def __init__(self, extra):
        self.extra = extra

    @staticmethod
    def get(extra):
        if not extra:
            return None

        e = session.query(Extra).filter(Extra.extra == extra).first()
        if e:
            return e

        e = Extra(extra)
        session.add(e)
        session.commit()

        return e

    @staticmethod
    def dump():
        for x in session.query(Extra):
            print(x)

    def __repr__(self):
        return self.extra

    def __str__(self):
        return self.__repr__()


class SentEmail(Base):
    __tablename__ = 'sentemails'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tool_id = Column(Integer, ForeignKey('tools.id', ondelete='CASCADE'))
    email_id = Column(Integer, ForeignKey('emails.id', ondelete='CASCADE'))
    extra_id = Column(Integer, ForeignKey('extras.id', ondelete='CASCADE'))
    date = Column(Integer)

    def __init__(self, tool, date, email, extra):
        self.tool = tool if isinstance(tool, Tool) else Tool.get(tool)
        self.date = get_ts(date)
        self.email = Email.get(email)
        self.extra = Extra.get(extra)

    def get_date(self):
        return lmdutils.get_date_from_timestamp(self.date)

    @staticmethod
    def dump(path=''):
        res = session.query(SentEmail).join(SentEmail.tool).join(SentEmail.email)
        ext = os.path.splitext(path)[1]
        if ext == '.csv':
            with open(path, 'w') as Out:
                writer = csv.writer(Out, delimiter=',')
                writer.writerow(['Tool', 'email', 'Date', 'Extra'])
                for x in res:
                    extra = x.extra.extra if x.extra else ''
                    writer.writerow(
                        [x.tool.name, x.email.email, str(x.get_date()), extra]
                    )
        elif ext == '.json':
            with open(path, 'w') as Out:
                data = []
                for x in res:
                    extra = x.extra.extra if x.extra else ''
                    data.append(
                        {
                            'tool': x.tool.name,
                            'email': x.email.email,
                            'date': str(x.get_date()),
                            'extra': x.extra,
                        }
                    )
                json.dump(data, Out)
        else:
            for x in res:
                print(x)

    @staticmethod
    def read_from(path):
        ext = os.path.splitext(path)[1]
        if ext == '.csv':
            with open(path, 'r') as In:
                reader = csv.reader(In, delimiter=',')
                for tool, email, date, extra in reader:
                    session.add(SentEmail(tool, date, email, extra))
                session.commit()
        elif ext == '.json':
            with open(path, 'r') as In:
                data = json.load(In)
                for x in data:
                    tool, date, bugid, extra = (
                        x[f] for f in ['tool', 'date', 'email', 'extra']
                    )
                    session.add(SentEmail(tool, date, email, extra))
                session.commit()
        else:
            assert False, 'Unable to read file: {}'.format(path)

    @staticmethod
    def add(tool, mails, extra, ts=lmdutils.get_timestamp('now')):
        with FileLock(lock_path):
            tool = Tool.get(tool)
            for mail in mails:
                session.add(SentEmail(tool, ts, mail, extra))
            session.commit()

    @staticmethod
    def get(name=None, start_date=None, end_date=None, first=False):
        start_date = get_ts(start_date, 0)
        end_date = get_ts(start_date, 'now')
        with FileLock(lock_path):
            if name:
                rs = (
                    session.query(SentEmail)
                    .join(SentEmail.tool)
                    .filter(
                        Tool.name == name,
                        SentEmail.date >= start_date,
                        SentEmail.date < end_date,
                    )
                )
            else:
                rs = session.query(SentEmail).filter(
                    SentEmail.date >= start_date, SentEmail.date < end_date
                )

            if first:
                return rs.first()

            return [r for r in rs]

    @staticmethod
    def has_already_nagged(name=None, start_date=None, end_date=None):
        return (
            SentEmail.get(
                name=name, start_date=start_date, end_date=end_date, first=True
            )
            is not None
        )

    def __repr__(self):
        extra = self.extra.extra if self.extra else ''
        return '<Email ({}) sent for {}: to {}, the {}, extra={}>'.format(
            self.extra, self.tool, self.email, self.get_date(), extra
        )

    def __str__(self):
        return self.__repr__()
