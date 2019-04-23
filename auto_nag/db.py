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
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import Column, ForeignKey, Integer, String

from auto_nag import logger, utils
from auto_nag.history import History


Base = declarative_base()
lock_path = utils.get_config('common', 'lock')
db_url = utils.get_config('common', 'database')
engine = create_engine(db_url)
DBSession = sessionmaker(bind=engine)
Base.metadata.bind = engine
session = DBSession()


def init():
    hist = History().get()
    logger.info('Put history in db: start...')
    BugChange.import_from_dict(hist)
    logger.info('Put history in db: end.')


def check(table_name):
    if not engine.dialect.has_table(engine, table_name):
        raise Exception(
            'No database here: you can create it in using \'alembic upgrade head\' and you can fill it with Bugzilla data in calling auto_nag.db.init()'
        )


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
    __tablename__ = 'autonag_tools'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True)
    bugchanges = relationship('BugChange', backref='tool')
    emails = relationship('Email', backref='tool')

    def __init__(self, name):
        self.name = name

    @staticmethod
    def get_or_create(name):
        try:
            return session.query(Tool).filter(Tool.name == name).one()
        except NoResultFound:
            e = Tool(name)
            session.add(e)
            session.commit()

            return e

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.__repr__()


class BugChange(Base):
    __tablename__ = 'autonag_bugchanges'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tool_id = Column(Integer, ForeignKey('autonag_tools.id', ondelete='CASCADE'))
    extra_id = Column(Integer, ForeignKey('autonag_extras.id', ondelete='CASCADE'))
    date = Column(Integer)
    bugid = Column(Integer)

    def __init__(self, tool, date, bugid, extra):
        self.tool = Tool.get_or_create(tool)
        self.date = get_ts(date)
        self.bugid = int(bugid)
        self.extra = Extra.get_or_create(extra)

    def get_date(self):
        return lmdutils.get_date_from_timestamp(self.date)

    @staticmethod
    def add(tool, bugid, ts=lmdutils.get_timestamp('now'), extra=''):
        check(BugChange.__tablename__)
        with FileLock(lock_path):
            session.add(BugChange(tool, ts, bugid, extra))
            session.commit()

    @staticmethod
    def get(name=None, start_date=None, end_date=None):
        with FileLock(lock_path):
            start_date = get_ts(start_date, default=0)
            end_date = get_ts(end_date, default='now')
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

            return rs

    @staticmethod
    def has_already_nagged(bugids, name=None, start_date=None, end_date=None):
        with FileLock(lock_path):
            data = {int(bugid): False for bugid in bugids}
            bugids = list(data.keys())
            start_date = get_ts(start_date, default=0)
            end_date = get_ts(end_date, default='now')
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
    def import_from_dict(data):
        for x in data:
            tool, date, bugid, extra = (
                x[f] for f in ['tool', 'date', 'bugid', 'extra']
            )
            session.add(BugChange(tool, date, bugid, extra))
        session.commit()

    def __repr__(self):
        extra = self.extra.extra if self.extra else ''
        return '<Bug change ({}): bug {}, the {}, extra={}>'.format(
            self.tool, self.bugid, self.get_date(), extra
        )

    def __str__(self):
        return self.__repr__()


class User(Base):
    __tablename__ = 'autonag_users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(254), unique=True)
    mails = relationship('Email', backref='user')

    def __init__(self, email):
        self.email = email

    @staticmethod
    def get_or_create(email):
        try:
            return session.query(User).filter(User.email == email).one()
        except NoResultFound:
            e = User(email)
            session.add(e)
            session.commit()

            return e

    @staticmethod
    def dump():
        for x in session.query(User):
            print(x)

    def __repr__(self):
        return self.email

    def __str__(self):
        return self.__repr__()


class Extra(Base):
    __tablename__ = 'autonag_extras'

    id = Column(Integer, primary_key=True, autoincrement=True)
    extra = Column(String(256), unique=True)
    mails = relationship('Email', backref='extra')
    bugchanges = relationship('BugChange', backref='extra')

    def __init__(self, extra):
        self.extra = extra

    @staticmethod
    def get_or_create(extra):
        try:
            return (
                session.query(Extra).filter(Extra.extra == extra).one()
                if extra
                else None
            )
        except NoResultFound:
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


class Email(Base):
    __tablename__ = 'autonag_emails'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tool_id = Column(Integer, ForeignKey('autonag_tools.id', ondelete='CASCADE'))
    user_id = Column(Integer, ForeignKey('autonag_users.id', ondelete='CASCADE'))
    extra_id = Column(Integer, ForeignKey('autonag_extras.id', ondelete='CASCADE'))
    date = Column(Integer)
    result = Column(Integer)

    def __init__(self, tool, date, user, extra, result):
        self.tool = tool if isinstance(tool, Tool) else Tool.get_or_create(tool)
        self.date = get_ts(date)
        self.user = User.get_or_create(user)
        self.extra = Extra.get_or_create(extra)
        self.result = 0 if result.lower() == 'failure' else 1

    def get_date(self):
        return lmdutils.get_date_from_timestamp(self.date)

    @staticmethod
    def dump(path=''):
        res = session.query(Email).join(Email.tool).join(Email.user)
        ext = os.path.splitext(path)[1]
        if ext == '.csv':
            with open(path, 'w') as Out:
                writer = csv.writer(Out, delimiter=',')
                writer.writerow(['Tool', 'User', 'Date', 'Extra', 'Result'])
                for x in res:
                    extra = x.extra.extra if x.extra else ''
                    res = 'Success' if x.result != 0 else 'Failure'
                    writer.writerow(
                        [x.tool.name, x.user.email, str(x.get_date()), extra, res]
                    )
        elif ext == '.json':
            with open(path, 'w') as Out:
                data = []
                for x in res:
                    extra = x.extra.extra if x.extra else ''
                    res = 'Success' if x.result != 0 else 'Failure'
                    data.append(
                        {
                            'tool': x.tool.name,
                            'user': x.user.email,
                            'date': str(x.get_date()),
                            'extra': extra,
                            'result': res,
                        }
                    )
                json.dump(data, Out)
        else:
            for x in res:
                print(x)

    @staticmethod
    def import_from_dict(data):
        for x in data:
            tool, date, user, extra, result = (
                x[f] for f in ['tool', 'date', 'user', 'extra', 'result']
            )
            session.add(Email(tool, date, user, extra, result))
        session.commit()

    @staticmethod
    def add(tool, mails, extra, result, ts=lmdutils.get_timestamp('now')):
        check(Email.__tablename__)
        with FileLock(lock_path):
            tool = Tool.get_or_create(tool)
            for mail in mails:
                session.add(Email(tool, ts, mail, extra, result))
            session.commit()

    @staticmethod
    def get(name=None, start_date=None, end_date=None):
        start_date = get_ts(start_date, 0)
        end_date = get_ts(end_date, 'now')
        with FileLock(lock_path):
            if name:
                rs = (
                    session.query(Email)
                    .join(Email.tool)
                    .filter(
                        Tool.name == name,
                        Email.date >= start_date,
                        Email.date < end_date,
                    )
                )
            else:
                rs = session.query(Email).filter(
                    Email.date >= start_date, Email.date < end_date
                )

            return rs

    @staticmethod
    def has_already_nagged(name=None, start_date=None, end_date=None):
        return (
            Email.get(name=name, start_date=start_date, end_date=end_date).first()
            is not None
        )

    def __repr__(self):
        extra = self.extra.extra if self.extra else ''
        res = 'Success' if self.result != 0 else 'Failure'
        return '<Email ({}) sent for {}: to {}, the {}, extra={}, result={}>'.format(
            self.extra, self.tool, self.user.email, self.get_date(), extra, res
        )

    def __str__(self):
        return self.__repr__()
